import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.connectors.base import BaseConnector, RawResult
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class OpenAlexConnector(BaseConnector):
    """
    OpenAlex Scholarly Works Connector.
    Uses the official OpenAlex REST API: https://api.openalex.org/works
    Free & open, optional API key or mailto for polite pool.
    """
    source_id = "openalex"
    name = "OpenAlex Scholarly Works"
    category = "academic"
    requires_auth = False
    supported_content_types = ["paper", "article", "preprint"]

    BASE_URL = "https://api.openalex.org/works"

    def __init__(self):
        self._last_diagnostic: Optional[Dict[str, Any]] = None

    @property
    def rate_limit_per_minute(self) -> int:
        return 100 if settings.OPENALEX_API_KEY else 50

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "User-Agent": "MultiSource-AI-Research-Engine/1.0"
        }
        if settings.OPENALEX_API_KEY:
            headers["api-key"] = settings.OPENALEX_API_KEY
        return headers

    async def test_connection(self) -> Dict[str, Any]:
        now_str = datetime.utcnow().isoformat()
        try:
            params = {"per-page": 1}
            if settings.OPENALEX_EMAIL:
                params["mailto"] = settings.OPENALEX_EMAIL

            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.get(self.BASE_URL, headers=self._get_headers(), params=params)

                if resp.status_code == 200:
                    diag = {
                        "configured": True,
                        "authorized": True,
                        "connected": True,
                        "status": "connected",
                        "message": "OpenAlex REST API operational" + (" (polite pool active)" if settings.OPENALEX_EMAIL else ""),
                        "last_checked_at": now_str
                    }
                    self._last_diagnostic = diag
                    return diag
                elif resp.status_code == 429:
                    diag = {
                        "configured": True,
                        "authorized": True,
                        "connected": False,
                        "status": "rate_limited",
                        "message": "OpenAlex rate limit exceeded",
                        "last_checked_at": now_str
                    }
                    self._last_diagnostic = diag
                    return diag
                else:
                    diag = {
                        "configured": True,
                        "authorized": False,
                        "connected": False,
                        "status": "error",
                        "message": f"OpenAlex returned HTTP {resp.status_code}",
                        "last_checked_at": now_str
                    }
                    self._last_diagnostic = diag
                    return diag
        except Exception as e:
            diag = {
                "configured": True,
                "authorized": False,
                "connected": False,
                "status": "error",
                "message": f"Network error testing OpenAlex: {str(e)}",
                "last_checked_at": now_str
            }
            self._last_diagnostic = diag
            return diag

    def check_health(self) -> Dict[str, Any]:
        if self._last_diagnostic:
            return {
                "status": self._last_diagnostic.get("status", "operational"),
                "auth_status": "configured" if settings.OPENALEX_API_KEY else "not_required",
                "message": self._last_diagnostic.get("message", "OpenAlex operational")
            }
        return {
            "status": "operational",
            "auth_status": "configured" if settings.OPENALEX_API_KEY else "not_required",
            "message": "OpenAlex public API ready (polite pool compatible)"
        }

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        results: List[RawResult] = []
        params = {
            "search": query,
            "per-page": min(limit, 25),
            "select": "id,title,doi,publication_year,publication_date,authorships,cited_by_count,primary_location,open_access,abstract_inverted_index"
        }
        if settings.OPENALEX_EMAIL:
            params["mailto"] = settings.OPENALEX_EMAIL

        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.get(self.BASE_URL, headers=self._get_headers(), params=params)
                if resp.status_code != 200:
                    logger.warning(f"OpenAlex search returned status {resp.status_code}")
                    return []

                data = resp.json()
                for item in data.get("results", []):
                    title = item.get("title")
                    if not title:
                        continue

                    doi = item.get("doi")
                    work_id = item.get("id", "").split("/")[-1]
                    url = doi or item.get("id") or f"https://openalex.org/{work_id}"

                    # Authors
                    authors_list = []
                    for auth in item.get("authorships", []):
                        aname = auth.get("author", {}).get("display_name")
                        if aname:
                            authors_list.append(aname)
                    authors_str = ", ".join(authors_list[:4]) if authors_list else None

                    # Publication date
                    pub_date_str = item.get("publication_date")
                    pub = None
                    if pub_date_str:
                        try:
                            pub = datetime.fromisoformat(pub_date_str)
                        except Exception:
                            pass

                    # Reconstruct snippet from abstract_inverted_index if present
                    snippet = ""
                    inv_index = item.get("abstract_inverted_index")
                    if inv_index:
                        try:
                            words_by_pos = []
                            for word, positions in inv_index.items():
                                for pos in positions:
                                    words_by_pos.append((pos, word))
                            words_by_pos.sort(key=lambda x: x[0])
                            full_abstract = " ".join(w[1] for w in words_by_pos)
                            snippet = (full_abstract[:280] + "...") if len(full_abstract) > 280 else full_abstract
                        except Exception:
                            snippet = ""

                    if not snippet:
                        source_name = item.get("primary_location", {}).get("source", {}).get("display_name") or "Scholarly literature"
                        snippet = f"Research work published in {item.get('publication_year', 'recent years')} ({source_name})."

                    citations = item.get("cited_by_count", 0)
                    is_oa = item.get("open_access", {}).get("is_oa", False)

                    results.append(
                        RawResult(
                            source_name="openalex",
                            source_item_id=str(work_id),
                            title=title,
                            content_snippet=snippet,
                            source_url=url,
                            author=authors_str,
                            published_at=pub,
                            content_type="paper",
                            engagement_metrics={
                                "citation_count": citations,
                                "is_open_access": is_oa
                            },
                            metadata={
                                "doi": doi,
                                "publication_year": item.get("publication_year")
                            }
                        )
                    )

        except Exception as e:
            logger.error(f"OpenAlex search failed: {e}")

        return results
