import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.connectors.base import BaseConnector, RawResult
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class InternetArchiveConnector(BaseConnector):
    """
    Internet Archive Connector.
    Uses the official Advanced Search API: https://archive.org/advancedsearch.php
    Does not require authentication for public metadata search.
    """
    source_id = "internet_archive"
    name = "Internet Archive"
    category = "archive"
    requires_auth = False
    supported_content_types = ["document", "media", "metadata"]

    SEARCH_URL = "https://archive.org/advancedsearch.php"

    def __init__(self):
        self._last_diagnostic: Optional[Dict[str, Any]] = None

    @property
    def rate_limit_per_minute(self) -> int:
        return 30

    async def test_connection(self) -> Dict[str, Any]:
        now_str = datetime.utcnow().isoformat()
        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                params = {
                    "q": "collection:opensource",
                    "rows": 1,
                    "output": "json"
                }
                resp = await client.get(self.SEARCH_URL, params=params)
                if resp.status_code == 200:
                    diag = {
                        "configured": True,
                        "authorized": True,
                        "connected": True,
                        "status": "connected",
                        "message": "Internet Archive Advanced Search API operational",
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
                        "message": "Internet Archive rate limit reached",
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
                        "message": f"Internet Archive returned HTTP {resp.status_code}",
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
                "message": f"Network error testing Internet Archive: {str(e)}",
                "last_checked_at": now_str
            }
            self._last_diagnostic = diag
            return diag

    def check_health(self) -> Dict[str, Any]:
        if self._last_diagnostic:
            return {
                "status": self._last_diagnostic.get("status", "operational"),
                "auth_status": "not_required",
                "message": self._last_diagnostic.get("message", "Internet Archive operational")
            }
        return {
            "status": "operational",
            "auth_status": "not_required",
            "message": "Internet Archive public metadata API ready"
        }

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        results: List[RawResult] = []
        params = {
            "q": query,
            "fl[]": ["identifier", "title", "description", "creator", "date", "mediatype", "downloads"],
            "rows": min(limit, 30),
            "output": "json"
        }

        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.get(self.SEARCH_URL, params=params)
                if resp.status_code != 200:
                    logger.warning(f"Internet Archive search failed with status {resp.status_code}")
                    return []

                data = resp.json()
                docs = data.get("response", {}).get("docs", [])
                for doc in docs:
                    identifier = doc.get("identifier")
                    if not identifier:
                        continue

                    title = doc.get("title") or identifier
                    # Can be list or string
                    if isinstance(title, list):
                        title = title[0] if title else identifier

                    desc = doc.get("description", "")
                    if isinstance(desc, list):
                        desc = " ".join(desc)

                    snippet = (desc[:280] + "...") if len(desc) > 280 else desc
                    mediatype = doc.get("mediatype", "texts")
                    url = f"https://archive.org/details/{identifier}"

                    creator = doc.get("creator")
                    if isinstance(creator, list):
                        creator = ", ".join(creator)

                    date_str = doc.get("date")
                    pub = None
                    if date_str:
                        try:
                            pub = datetime.fromisoformat(str(date_str)[:10])
                        except Exception:
                            pass

                    downloads = doc.get("downloads", 0)

                    results.append(
                        RawResult(
                            source_name="internet_archive",
                            source_item_id=str(identifier),
                            title=title,
                            content_snippet=snippet or f"Archived {mediatype} record on archive.org",
                            source_url=url,
                            author=creator,
                            published_at=pub,
                            content_type=mediatype if mediatype in ("texts", "audio", "video") else "document",
                            engagement_metrics={"downloads": downloads},
                            metadata={"mediatype": mediatype}
                        )
                    )

        except Exception as e:
            logger.error(f"Internet Archive search failed: {e}")

        return results
