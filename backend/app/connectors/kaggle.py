import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.connectors.base import BaseConnector, RawResult
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class KaggleConnector(BaseConnector):
    """
    Kaggle Datasets & Metadata Connector.
    Uses the official Kaggle REST API v1 (https://www.kaggle.com/api/v1).
    Authenticates using HTTP Basic Auth with KAGGLE_USERNAME and KAGGLE_KEY.
    """
    source_id = "kaggle"
    name = "Kaggle Datasets"
    category = "datasets"
    requires_auth = True
    supported_content_types = ["dataset", "metadata"]

    BASE_URL = "https://www.kaggle.com/api/v1/datasets/list"

    def __init__(self):
        self._last_diagnostic: Optional[Dict[str, Any]] = None

    @property
    def rate_limit_per_minute(self) -> int:
        return 30

    def is_configured(self) -> bool:
        return bool(settings.KAGGLE_USERNAME and settings.KAGGLE_KEY)

    async def test_connection(self) -> Dict[str, Any]:
        now_str = datetime.utcnow().isoformat()
        if not self.is_configured():
            diag = {
                "configured": False,
                "authorized": False,
                "connected": False,
                "status": "not_configured",
                "message": "Missing KAGGLE_USERNAME or KAGGLE_KEY in backend .env",
                "last_checked_at": now_str,
                "details": {
                    "username_set": bool(settings.KAGGLE_USERNAME),
                    "key_set": bool(settings.KAGGLE_KEY)
                }
            }
            self._last_diagnostic = diag
            return diag

        auth = httpx.BasicAuth(settings.KAGGLE_USERNAME.strip(), settings.KAGGLE_KEY.strip())
        headers = {"User-Agent": "MultiSource-AI-Research-Engine/1.0"}

        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.get(
                    self.BASE_URL,
                    auth=auth,
                    headers=headers,
                    params={"page": 1, "pageSize": 1}
                )

                if resp.status_code == 200:
                    diag = {
                        "configured": True,
                        "authorized": True,
                        "connected": True,
                        "status": "connected",
                        "message": "Successfully authenticated with Kaggle API",
                        "last_checked_at": now_str
                    }
                    self._last_diagnostic = diag
                    return diag
                elif resp.status_code in (401, 403):
                    diag = {
                        "configured": True,
                        "authorized": False,
                        "connected": False,
                        "status": "pending_authorization",
                        "message": f"Kaggle authentication rejected ({resp.status_code}). Verify KAGGLE_USERNAME and KAGGLE_KEY.",
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
                        "message": "Kaggle API rate limit exceeded.",
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
                        "message": f"Kaggle API returned HTTP {resp.status_code}",
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
                "message": f"Network error connecting to Kaggle: {str(e)}",
                "last_checked_at": now_str
            }
            self._last_diagnostic = diag
            return diag

    def check_health(self) -> Dict[str, Any]:
        if not self.is_configured():
            return {
                "status": "not_configured",
                "auth_status": "not_configured",
                "message": "Missing KAGGLE_USERNAME and KAGGLE_KEY in .env"
            }
        if self._last_diagnostic:
            return {
                "status": self._last_diagnostic.get("status", "configured"),
                "auth_status": "authorized" if self._last_diagnostic.get("authorized") else self._last_diagnostic.get("status"),
                "message": self._last_diagnostic.get("message", "Kaggle API configured")
            }
        return {
            "status": "configured",
            "auth_status": "configured",
            "message": "Kaggle credentials present (ready for connection test)"
        }

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        if not self.is_configured():
            logger.info("Kaggle search skipped: credentials not configured")
            return []

        results: List[RawResult] = []
        auth = httpx.BasicAuth(settings.KAGGLE_USERNAME.strip(), settings.KAGGLE_KEY.strip())
        headers = {"User-Agent": "MultiSource-AI-Research-Engine/1.0"}
        params = {
            "search": query,
            "page": 1,
            "pageSize": min(limit, 30),
            "sortBy": "relevance"
        }

        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.get(self.BASE_URL, auth=auth, headers=headers, params=params)

                if resp.status_code != 200:
                    logger.warning(f"Kaggle search returned status {resp.status_code}")
                    return []

                datasets = resp.json()
                for d in datasets:
                    ref = d.get("ref", "")
                    title = d.get("title") or ref
                    subtitle = d.get("subtitle") or ""
                    url = f"https://www.kaggle.com/datasets/{ref}" if ref else "https://www.kaggle.com/datasets"
                    
                    creator_name = d.get("creatorName") or d.get("ownerName")
                    last_updated = d.get("lastUpdated")
                    pub = None
                    if last_updated:
                        try:
                            pub = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
                        except Exception:
                            pass

                    votes = d.get("voteCount", 0)
                    downloads = d.get("downloadCount", 0)
                    usability = d.get("usabilityRating", 0)

                    snippet = subtitle if subtitle else f"Kaggle dataset: {ref}. Usability rating: {usability}."

                    results.append(
                        RawResult(
                            source_name="kaggle",
                            source_item_id=str(d.get("id") or ref),
                            title=title,
                            content_snippet=snippet,
                            source_url=url,
                            author=creator_name,
                            published_at=pub,
                            content_type="dataset",
                            engagement_metrics={
                                "vote_count": votes,
                                "download_count": downloads,
                                "usability_rating": usability
                            },
                            metadata={
                                "ref": ref,
                                "is_private": d.get("isPrivate", False),
                                "total_bytes": d.get("totalBytes", 0)
                            }
                        )
                    )

        except Exception as e:
            logger.error(f"Kaggle search failed: {e}")

        return results
