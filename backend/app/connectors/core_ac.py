import httpx
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.connectors.base import BaseConnector, RawResult
from app.core.config import settings

logger = logging.getLogger(__name__)


class CoreACConnector(BaseConnector):
    """
    CORE Open Access Research Connector.
    Uses the official CORE API v3 (https://core.ac.uk/services/api).
    Requires a free API key — register at https://core.ac.uk/services/api.
    """
    source_id = "core"
    name = "CORE Open Access"
    category = "academic"
    requires_auth = True
    supported_content_types = ["paper", "article"]

    BASE_URL = "https://api.core.ac.uk/v3/search/works"

    def __init__(self):
        self._last_diagnostic: Optional[Dict[str, Any]] = None

    @property
    def rate_limit_per_minute(self) -> int:
        return 10

    def is_configured(self) -> bool:
        return bool(settings.CORE_API_KEY)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.CORE_API_KEY}",
            "User-Agent": "MultiSource-AI-Research-Engine/1.0",
        }

    async def test_connection(self) -> Dict[str, Any]:
        now_str = datetime.now(timezone.utc).isoformat()
        if not self.is_configured():
            diag = {
                "configured": False, "authorized": False, "connected": False,
                "status": "not_configured",
                "message": "Missing CORE_API_KEY in .env. Register free at https://core.ac.uk/services/api",
                "last_checked_at": now_str,
            }
            self._last_diagnostic = diag
            return diag
        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.get(
                    self.BASE_URL,
                    headers=self._headers(),
                    params={"q": "machine learning", "limit": 1}
                )
            if resp.status_code == 200:
                diag = {
                    "configured": True, "authorized": True, "connected": True,
                    "status": "connected",
                    "message": "CORE API authenticated and reachable",
                    "last_checked_at": now_str,
                }
            elif resp.status_code in (401, 403):
                diag = {
                    "configured": True, "authorized": False, "connected": False,
                    "status": "pending_authorization",
                    "message": f"CORE API rejected the key (HTTP {resp.status_code}). Verify CORE_API_KEY.",
                    "last_checked_at": now_str,
                }
            elif resp.status_code == 429:
                diag = {
                    "configured": True, "authorized": True, "connected": False,
                    "status": "rate_limited",
                    "message": "CORE API rate limit exceeded (10 req/min on free tier).",
                    "last_checked_at": now_str,
                }
            else:
                diag = {
                    "configured": True, "authorized": False, "connected": False,
                    "status": "error",
                    "message": f"CORE API returned HTTP {resp.status_code}",
                    "last_checked_at": now_str,
                }
        except Exception as e:
            diag = {
                "configured": self.is_configured(), "authorized": False, "connected": False,
                "status": "error",
                "message": f"Network error connecting to CORE: {e}",
                "last_checked_at": now_str,
            }
        self._last_diagnostic = diag
        return diag

    def check_health(self) -> Dict[str, Any]:
        if not self.is_configured():
            return {
                "status": "not_configured",
                "auth_status": "not_configured",
                "message": "Missing CORE_API_KEY in .env — register free at https://core.ac.uk/services/api",
            }
        if self._last_diagnostic:
            return {
                "status": self._last_diagnostic.get("status", "configured"),
                "auth_status": "authorized" if self._last_diagnostic.get("authorized") else self._last_diagnostic.get("status"),
                "message": self._last_diagnostic.get("message", ""),
            }
        return {
            "status": "configured",
            "auth_status": "configured",
            "message": "CORE API key present (run connection test to verify)",
        }

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        if not self.is_configured():
            logger.info("CORE search skipped: CORE_API_KEY not configured")
            return []

        results: List[RawResult] = []
        params = {"q": query, "limit": min(limit, 100), "sort": "relevance"}

        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.get(self.BASE_URL, headers=self._headers(), params=params)
            if resp.status_code != 200:
                logger.warning(f"CORE search returned {resp.status_code}")
                return []
            data = resp.json()
            for item in data.get("results", []):
                core_id = str(item.get("id", ""))
                title = item.get("title") or "Untitled"
                abstract = item.get("abstract") or ""
                download_url = item.get("downloadUrl")
                doi = item.get("doi")
                url = download_url or (f"https://doi.org/{doi}" if doi else f"https://core.ac.uk/works/{core_id}")

                authors_list = item.get("authors") or []
                if authors_list and isinstance(authors_list[0], dict):
                    author_str = ", ".join(a.get("name", "") for a in authors_list[:3]) or None
                else:
                    author_str = ", ".join(str(a) for a in authors_list[:3]) or None

                pub_date_str = item.get("publishedDate") or item.get("yearPublished")
                pub_at: Optional[datetime] = None
                if pub_date_str:
                    try:
                        pub_at = datetime.fromisoformat(str(pub_date_str)).replace(tzinfo=timezone.utc)
                    except Exception:
                        try:
                            pub_at = datetime(int(pub_date_str), 1, 1, tzinfo=timezone.utc)
                        except Exception:
                            pass

                results.append(RawResult(
                    source_name="core",
                    source_item_id=core_id,
                    title=title,
                    content_snippet=abstract[:500] if abstract else None,
                    source_url=url,
                    author=author_str,
                    published_at=pub_at,
                    content_type="paper",
                    engagement_metrics={},
                    metadata={
                        "doi": doi,
                        "publisher": item.get("publisher"),
                        "has_full_text": bool(download_url),
                        "language": item.get("language"),
                    },
                ))
        except Exception as e:
            logger.error(f"CORE search failed: {e}")
        return results
