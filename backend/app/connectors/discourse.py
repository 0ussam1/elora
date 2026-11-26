import httpx
import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.connectors.base import BaseConnector, RawResult
from app.core.config import settings

logger = logging.getLogger(__name__)

# Curated list of well-known public Discourse communities
DISCOURSE_INSTANCES = [
    "https://meta.discourse.org",
    "https://discuss.python.org",
    "https://community.openai.com",
    "https://forum.arduino.cc",
    "https://discourse.mozilla.org",
]


class DiscourseConnector(BaseConnector):
    """
    Discourse Forum Connector.
    Searches multiple public Discourse instances using the official search API.
    No authentication required for public forums.
    """
    source_id = "discourse"
    name = "Discourse Forums"
    category = "community"
    requires_auth = False
    supported_content_types = ["post", "discussion", "topic"]

    def __init__(self):
        self._last_diagnostic: Optional[Dict[str, Any]] = None

    @property
    def rate_limit_per_minute(self) -> int:
        return 20

    async def _search_instance(
        self,
        client: httpx.AsyncClient,
        instance: str,
        query: str,
        per_instance: int,
    ) -> List[RawResult]:
        """Search a single Discourse instance and return normalised results."""
        results: List[RawResult] = []
        try:
            resp = await client.get(
                f"{instance}/search.json",
                params={"q": query},
                headers={"User-Agent": "MultiSource-AI-Research-Engine/1.0"},
                timeout=8.0,
            )
            if resp.status_code != 200:
                logger.debug(f"Discourse {instance} returned {resp.status_code}")
                return []
            data = resp.json()
            topics = data.get("topics") or []
            for topic in topics[:per_instance]:
                topic_id = str(topic.get("id", ""))
                slug = topic.get("slug", topic_id)
                title = topic.get("title") or "Untitled"
                blurb = topic.get("blurb") or ""
                created_at_str = topic.get("created_at")
                pub_at: Optional[datetime] = None
                if created_at_str:
                    try:
                        pub_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                    except Exception:
                        pass
                url = f"{instance}/t/{slug}/{topic_id}"
                posts_count = topic.get("posts_count", 0)
                like_count = topic.get("like_count", 0)
                results.append(RawResult(
                    source_name="discourse",
                    source_item_id=f"{instance}_{topic_id}",
                    title=title,
                    content_snippet=blurb[:500] if blurb else None,
                    source_url=url,
                    author=None,
                    published_at=pub_at,
                    content_type="discussion",
                    engagement_metrics={
                        "posts_count": posts_count,
                        "like_count": like_count,
                        "views": topic.get("views", 0),
                    },
                    metadata={
                        "instance": instance,
                        "topic_id": topic_id,
                        "category_id": topic.get("category_id"),
                        "tags": topic.get("tags") or [],
                    },
                ))
        except Exception as e:
            logger.debug(f"Discourse {instance} search error: {e}")
        return results

    async def test_connection(self) -> Dict[str, Any]:
        now_str = datetime.now(timezone.utc).isoformat()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{DISCOURSE_INSTANCES[0]}/search.json",
                    params={"q": "hello"},
                    headers={"User-Agent": "MultiSource-AI-Research-Engine/1.0"},
                )
            if resp.status_code == 200:
                diag = {
                    "configured": True, "authorized": True, "connected": True,
                    "status": "connected",
                    "message": f"Discourse API reachable via {DISCOURSE_INSTANCES[0]}",
                    "last_checked_at": now_str,
                }
            else:
                diag = {
                    "configured": True, "authorized": False, "connected": False,
                    "status": "error",
                    "message": f"Discourse returned HTTP {resp.status_code}",
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
                "auth_status": "not_required",
                "message": self._last_diagnostic.get("message", ""),
            }
        return {
            "status": "operational",
            "auth_status": "not_required",
            "message": f"Discourse public search across {len(DISCOURSE_INSTANCES)} instances — no auth required",
        }

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        per_instance = max(1, limit // len(DISCOURSE_INSTANCES))
        async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
            tasks = [
                self._search_instance(client, inst, query, per_instance)
                for inst in DISCOURSE_INSTANCES
            ]
            groups = await asyncio.gather(*tasks, return_exceptions=True)
        results: List[RawResult] = []
        for group in groups:
            if isinstance(group, list):
                results.extend(group)
        return results[:limit]
