import httpx
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.connectors.base import BaseConnector, RawResult
from app.core.config import settings

logger = logging.getLogger(__name__)


class SemanticScholarConnector(BaseConnector):
    """
    Semantic Scholar Academic Paper Connector.
    Uses the official Semantic Scholar Graph API (https://api.semanticscholar.org).
    Free public access: 100 req/min. Optional API key for 10M req/month.
    """
    source_id = "semantic_scholar"
    name = "Semantic Scholar"
    category = "academic"
    requires_auth = False
    supported_content_types = ["paper", "article"]

    BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
    FIELDS = (
        "paperId,externalIds,title,abstract,authors,year,"
        "citationCount,influentialCitationCount,fieldsOfStudy,"
        "openAccessPdf,publicationDate"
    )

    def __init__(self):
        self._last_diagnostic: Optional[Dict[str, Any]] = None

    @property
    def rate_limit_per_minute(self) -> int:
        return 100 if not settings.SEMANTIC_SCHOLAR_API_KEY else 1000

    def _headers(self) -> Dict[str, str]:
        h = {"User-Agent": "MultiSource-AI-Research-Engine/1.0"}
        if settings.SEMANTIC_SCHOLAR_API_KEY:
            h["x-api-key"] = settings.SEMANTIC_SCHOLAR_API_KEY
        return h

    async def test_connection(self) -> Dict[str, Any]:
        now_str = datetime.now(timezone.utc).isoformat()
        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.get(
                    self.BASE_URL,
                    headers=self._headers(),
                    params={"query": "machine learning", "limit": 1, "fields": "paperId,title"}
                )
            if resp.status_code == 200:
                diag = {
                    "configured": True,
                    "authorized": True,
                    "connected": True,
                    "status": "connected",
                    "message": "Semantic Scholar API is reachable",
                    "last_checked_at": now_str,
                }
            elif resp.status_code == 429:
                diag = {
                    "configured": True, "authorized": True, "connected": False,
                    "status": "rate_limited",
                    "message": "Semantic Scholar rate limit exceeded",
                    "last_checked_at": now_str,
                }
            else:
                diag = {
                    "configured": True, "authorized": False, "connected": False,
                    "status": "error",
                    "message": f"Semantic Scholar API returned HTTP {resp.status_code}",
                    "last_checked_at": now_str,
                }
        except Exception as e:
            diag = {
                "configured": True, "authorized": False, "connected": False,
                "status": "error",
                "message": f"Network error: {e}",
                "last_checked_at": now_str,
            }
        self._last_diagnostic = diag
        return diag

    def check_health(self) -> Dict[str, Any]:
        if self._last_diagnostic:
            return {
                "status": self._last_diagnostic.get("status", "operational"),
                "auth_status": "authorized" if self._last_diagnostic.get("authorized") else "not_required",
                "message": self._last_diagnostic.get("message", ""),
            }
        return {
            "status": "operational",
            "auth_status": "not_required",
            "message": "Semantic Scholar public API — no key required (key optional for higher rate limits)",
        }

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        results: List[RawResult] = []
        params = {
            "query": query,
            "limit": min(limit, 100),
            "fields": self.FIELDS,
        }
        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.get(self.BASE_URL, headers=self._headers(), params=params)
            if resp.status_code != 200:
                logger.warning(f"SemanticScholar search returned {resp.status_code}")
                return []
            data = resp.json()
            for paper in data.get("data", []):
                paper_id = paper.get("paperId", "")
                title = paper.get("title") or "Untitled"
                abstract = paper.get("abstract") or ""
                year = paper.get("year")
                pub_date_str = paper.get("publicationDate")
                pub_at: Optional[datetime] = None
                if pub_date_str:
                    try:
                        pub_at = datetime.fromisoformat(pub_date_str).replace(tzinfo=timezone.utc)
                    except Exception:
                        pass
                elif year:
                    try:
                        pub_at = datetime(int(year), 1, 1, tzinfo=timezone.utc)
                    except Exception:
                        pass

                authors_list = paper.get("authors") or []
                author_str = ", ".join(a.get("name", "") for a in authors_list[:3]) or None

                open_pdf = paper.get("openAccessPdf") or {}
                pdf_url = open_pdf.get("url") if isinstance(open_pdf, dict) else None
                external_ids = paper.get("externalIds") or {}
                doi = external_ids.get("DOI")
                url = pdf_url or (f"https://doi.org/{doi}" if doi else f"https://www.semanticscholar.org/paper/{paper_id}")

                results.append(RawResult(
                    source_name="semantic_scholar",
                    source_item_id=paper_id,
                    title=title,
                    content_snippet=abstract[:500] if abstract else None,
                    source_url=url,
                    author=author_str,
                    published_at=pub_at,
                    content_type="paper",
                    engagement_metrics={
                        "citation_count": paper.get("citationCount", 0),
                        "influential_citation_count": paper.get("influentialCitationCount", 0),
                    },
                    metadata={
                        "doi": doi,
                        "fields_of_study": paper.get("fieldsOfStudy") or [],
                        "year": year,
                        "has_open_pdf": bool(pdf_url),
                    },
                ))
        except Exception as e:
            logger.error(f"SemanticScholar search failed: {e}")
        return results
