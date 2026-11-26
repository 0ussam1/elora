import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.connectors.base import BaseConnector, RawResult
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class OpenLibraryConnector(BaseConnector):
    """
    Open Library Books & Editions Connector.
    Uses the official Open Library Search API: https://openlibrary.org/search.json
    Free & open, no API key required for public catalog search.
    """
    source_id = "openlibrary"
    name = "Open Library Books"
    category = "books"
    requires_auth = False
    supported_content_types = ["book", "edition"]

    SEARCH_URL = "https://openlibrary.org/search.json"

    def __init__(self):
        self._last_diagnostic: Optional[Dict[str, Any]] = None

    @property
    def rate_limit_per_minute(self) -> int:
        return 40

    def _get_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": "MultiSource-AI-Research-Engine/1.0 (https://github.com/developer/research-engine)"
        }

    async def test_connection(self) -> Dict[str, Any]:
        now_str = datetime.now(timezone.utc).isoformat()
        try:
            params = {"q": "open source", "limit": 1}
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.get(self.SEARCH_URL, headers=self._get_headers(), params=params)

                if resp.status_code == 200:
                    diag = {
                        "configured": True,
                        "authorized": True,
                        "connected": True,
                        "status": "connected",
                        "message": "Open Library Search API operational",
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
                        "message": "Open Library rate limit reached",
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
                        "message": f"Open Library returned HTTP {resp.status_code}",
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
                "message": f"Network error testing Open Library: {str(e)}",
                "last_checked_at": now_str
            }
            self._last_diagnostic = diag
            return diag

    def check_health(self) -> Dict[str, Any]:
        if self._last_diagnostic:
            return {
                "status": self._last_diagnostic.get("status", "operational"),
                "auth_status": "not_required",
                "message": self._last_diagnostic.get("message", "Open Library operational")
            }
        return {
            "status": "operational",
            "auth_status": "not_required",
            "message": "Open Library book search API operational"
        }

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        results: List[RawResult] = []
        params = {
            "q": query,
            "limit": min(limit, 30),
            "fields": "key,title,author_name,first_publish_year,isbn,edition_count,subject,ratings_average,ratings_count"
        }

        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.get(self.SEARCH_URL, headers=self._get_headers(), params=params)
                if resp.status_code != 200:
                    logger.warning(f"Open Library search returned status {resp.status_code}")
                    return []

                data = resp.json()
                docs = data.get("docs", [])
                for doc in docs:
                    title = doc.get("title")
                    key = doc.get("key", "") # e.g. /works/OL45804W
                    if not title or not key:
                        continue

                    url = f"https://openlibrary.org{key}"
                    
                    authors = doc.get("author_name", [])
                    authors_str = ", ".join(authors[:3]) if authors else None

                    year = doc.get("first_publish_year")
                    pub = None
                    if year:
                        try:
                            pub = datetime(int(year), 1, 1)
                        except Exception:
                            pass

                    subjects = doc.get("subject", [])
                    subjects_str = ", ".join(subjects[:4]) if subjects else ""

                    edition_count = doc.get("edition_count", 1)
                    rating = doc.get("ratings_average")
                    ratings_count = doc.get("ratings_count", 0)

                    snippet = f"Book published first in {year or 'unknown year'}. {f'Subjects: {subjects_str}.' if subjects_str else ''} ({edition_count} editions)"

                    results.append(
                        RawResult(
                            source_name="openlibrary",
                            source_item_id=str(key.replace("/works/", "")),
                            title=title,
                            content_snippet=snippet,
                            source_url=url,
                            author=authors_str,
                            published_at=pub,
                            content_type="book",
                            engagement_metrics={
                                "rating": rating or 0,
                                "ratings_count": ratings_count,
                                "edition_count": edition_count
                            },
                            metadata={
                                "first_publish_year": year,
                                "isbn": doc.get("isbn", [])[:3] if doc.get("isbn") else []
                            }
                        )
                    )

        except Exception as e:
            logger.error(f"Open Library search failed: {e}")

        return results
