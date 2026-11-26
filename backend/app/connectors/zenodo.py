import httpx
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.connectors.base import BaseConnector, RawResult
from app.core.config import settings

logger = logging.getLogger(__name__)

# Zenodo resource_type.type → content_type mapping
_TYPE_MAP = {
    "publication": "paper",
    "dataset": "dataset",
    "software": "software",
    "image": "article",
    "video": "article",
    "presentation": "article",
    "poster": "article",
    "lesson": "article",
    "physicalobject": "dataset",
    "other": "article",
}


class ZenodoConnector(BaseConnector):
    """
    Zenodo Research Repository Connector.
    Uses the official Zenodo REST API (https://developers.zenodo.org).
    Free public access, no API key required for search.
    """
    source_id = "zenodo"
    name = "Zenodo"
    category = "academic"
    requires_auth = False
    supported_content_types = ["dataset", "paper", "article", "software"]

    BASE_URL = "https://zenodo.org/api/records"

    def __init__(self):
        self._last_diagnostic: Optional[Dict[str, Any]] = None

    @property
    def rate_limit_per_minute(self) -> int:
        return 60

    async def test_connection(self) -> Dict[str, Any]:
        now_str = datetime.now(timezone.utc).isoformat()
        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.get(
                    self.BASE_URL,
                    params={"q": "test", "size": 1, "sort": "bestmatch"},
                    headers={"User-Agent": "MultiSource-AI-Research-Engine/1.0"},
                )
            if resp.status_code == 200:
                diag = {
                    "configured": True, "authorized": True, "connected": True,
                    "status": "connected",
                    "message": "Zenodo API is reachable",
                    "last_checked_at": now_str,
                }
            elif resp.status_code == 429:
                diag = {
                    "configured": True, "authorized": True, "connected": False,
                    "status": "rate_limited",
                    "message": "Zenodo rate limit exceeded",
                    "last_checked_at": now_str,
                }
            else:
                diag = {
                    "configured": True, "authorized": False, "connected": False,
                    "status": "error",
                    "message": f"Zenodo API returned HTTP {resp.status_code}",
                    "last_checked_at": now_str,
                }
        except Exception as e:
            diag = {
                "configured": True, "authorized": False, "connected": False,
                "status": "error",
                "message": f"Network error connecting to Zenodo: {e}",
                "last_checked_at": now_str,
            }
        self._last_diagnostic = diag
        return diag

    def check_health(self) -> Dict[str, Any]:
        if self._last_diagnostic:
            return {
                "status": self._last_diagnostic.get("status", "operational"),
                "auth_status": "not_required",
                "message": self._last_diagnostic.get("message", ""),
            }
        return {
            "status": "operational",
            "auth_status": "not_required",
            "message": "Zenodo public API — no authentication required",
        }

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        results: List[RawResult] = []
        params = {
            "q": query,
            "size": min(limit, 100),
            "sort": "bestmatch",
        }
        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.get(
                    self.BASE_URL,
                    params=params,
                    headers={"User-Agent": "MultiSource-AI-Research-Engine/1.0"},
                )
            if resp.status_code != 200:
                logger.warning(f"Zenodo search returned {resp.status_code}")
                return []
            data = resp.json()
            for record in data.get("hits", {}).get("hits", []):
                record_id = str(record.get("id", ""))
                meta = record.get("metadata", {})
                title = meta.get("title") or "Untitled"
                description = meta.get("description") or ""
                doi = meta.get("doi")
                concept_doi = record.get("conceptdoi")
                links = record.get("links", {})
                url = links.get("html") or (f"https://doi.org/{doi}" if doi else f"https://zenodo.org/record/{record_id}")

                creators = meta.get("creators") or []
                author_str = ", ".join(c.get("name", "") for c in creators[:3]) or None

                pub_date_str = meta.get("publication_date")
                pub_at: Optional[datetime] = None
                if pub_date_str:
                    try:
                        pub_at = datetime.fromisoformat(pub_date_str).replace(tzinfo=timezone.utc)
                    except Exception:
                        pass

                res_type_obj = meta.get("resource_type") or {}
                res_type = res_type_obj.get("type", "other")
                content_type = _TYPE_MAP.get(res_type, "article")

                results.append(RawResult(
                    source_name="zenodo",
                    source_item_id=record_id,
                    title=title,
                    content_snippet=description[:500] if description else None,
                    source_url=url,
                    author=author_str,
                    published_at=pub_at,
                    content_type=content_type,
                    engagement_metrics={
                        "downloads": record.get("stats", {}).get("downloads", 0),
                        "views": record.get("stats", {}).get("views", 0),
                    },
                    metadata={
                        "doi": doi,
                        "concept_doi": concept_doi,
                        "resource_type": res_type,
                        "access_right": meta.get("access_right"),
                    },
                ))
        except Exception as e:
            logger.error(f"Zenodo search failed: {e}")
        return results
