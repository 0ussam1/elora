import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.connectors.base import BaseConnector, RawResult
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class CrossrefConnector(BaseConnector):
    """
    Crossref Scholarly Metadata Connector.
    Uses the official Crossref REST API: https://api.crossref.org/works
    Free & open, supports polite pool with identifying User-Agent / mailto.
    """
    source_id = "crossref"
    name = "Crossref Metadata"
    category = "academic"
    requires_auth = False
    supported_content_types = ["paper", "article", "proceedings", "book"]

    BASE_URL = "https://api.crossref.org/works"

    def __init__(self):
        self._last_diagnostic: Optional[Dict[str, Any]] = None

    @property
    def rate_limit_per_minute(self) -> int:
        return 50

    def _get_headers(self) -> Dict[str, str]:
        email = settings.CROSSREF_MAILTO or "user@example.com"
        return {
            "User-Agent": f"MultiSource-AI-Research-Engine/1.0 (mailto:{email})"
        }

    async def test_connection(self) -> Dict[str, Any]:
        now_str = datetime.now(timezone.utc).isoformat()
        try:
            params = {"rows": 1}
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.get(self.BASE_URL, headers=self._get_headers(), params=params)

                if resp.status_code == 200:
                    diag = {
                        "configured": True,
                        "authorized": True,
                        "connected": True,
                        "status": "connected",
                        "message": "Crossref REST API operational (polite pool active)",
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
                        "message": "Crossref API rate limit reached",
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
                        "message": f"Crossref API returned HTTP {resp.status_code}",
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
                "message": f"Network error testing Crossref: {str(e)}",
                "last_checked_at": now_str
            }
            self._last_diagnostic = diag
            return diag

    def check_health(self) -> Dict[str, Any]:
        if self._last_diagnostic:
            return {
                "status": self._last_diagnostic.get("status", "operational"),
                "auth_status": "not_required",
                "message": self._last_diagnostic.get("message", "Crossref operational")
            }
        return {
            "status": "operational",
            "auth_status": "not_required",
            "message": "Crossref official REST API operational (polite pool enabled)"
        }

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        results: List[RawResult] = []
        params = {
            "query": query,
            "rows": min(limit, 25),
            "select": "DOI,title,author,abstract,publisher,published,URL,is-referenced-by-count,type"
        }

        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.get(self.BASE_URL, headers=self._get_headers(), params=params)
                if resp.status_code != 200:
                    logger.warning(f"Crossref search returned status {resp.status_code}")
                    return []

                data = resp.json()
                items = data.get("message", {}).get("items", [])
                for item in items:
                    title_list = item.get("title", [])
                    title = title_list[0] if title_list else item.get("DOI")
                    if not title:
                        continue

                    doi = item.get("DOI")
                    url = item.get("URL") or (f"https://doi.org/{doi}" if doi else "")
                    
                    # Authors
                    authors_list = []
                    for a in item.get("author", []):
                        given = a.get("given", "")
                        family = a.get("family", "")
                        full_name = f"{given} {family}".strip()
                        if full_name:
                            authors_list.append(full_name)
                    authors_str = ", ".join(authors_list[:4]) if authors_list else None

                    # Publication date
                    pub_date_parts = item.get("published", {}).get("date-parts", [[]])[0]
                    pub = None
                    if pub_date_parts:
                        try:
                            year = pub_date_parts[0]
                            month = pub_date_parts[1] if len(pub_date_parts) > 1 else 1
                            day = pub_date_parts[2] if len(pub_date_parts) > 2 else 1
                            pub = datetime(year, month, day)
                        except Exception:
                            pass

                    # Clean abstract (Crossref abstracts often contain JATS XML tags like <jats:p>)
                    abstract_raw = item.get("abstract", "")
                    import re
                    clean_abstract = re.sub(r'<[^>]+>', '', abstract_raw).strip()
                    snippet = (clean_abstract[:280] + "...") if len(clean_abstract) > 280 else clean_abstract

                    publisher = item.get("publisher", "")
                    if not snippet:
                        snippet = f"Scholarly publication published by {publisher}. DOI: {doi}"

                    citations = item.get("is-referenced-by-count", 0)
                    content_type = item.get("type", "journal-article")

                    results.append(
                        RawResult(
                            source_name="crossref",
                            source_item_id=str(doi or url),
                            title=title,
                            content_snippet=snippet,
                            source_url=url,
                            author=authors_str,
                            published_at=pub,
                            content_type="paper" if "article" in content_type else "article",
                            engagement_metrics={"citations": citations},
                            metadata={
                                "doi": doi,
                                "publisher": publisher,
                                "original_type": content_type
                            }
                        )
                    )

        except Exception as e:
            logger.error(f"Crossref search failed: {e}")

        return results
