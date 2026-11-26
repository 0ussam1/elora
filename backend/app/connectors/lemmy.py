import httpx
import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.connectors.base import BaseConnector, RawResult
from app.core.config import settings

logger = logging.getLogger(__name__)

# Curated list of large public Lemmy instances
LEMMY_INSTANCES = [
    "https://lemmy.world",
    "https://lemmy.ml",
    "https://beehaw.org",
]


class LemmyConnector(BaseConnector):
    """
    Lemmy Federated Community Connector.
    Searches multiple public Lemmy instances using the official Lemmy API v3.
    No authentication required for public search.
    """
    source_id = "lemmy"
    name = "Lemmy Communities"
    category = "community"
    requires_auth = False
    supported_content_types = ["post", "discussion"]

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
        results: List[RawResult] = []
        try:
            resp = await client.get(
                f"{instance}/api/v3/search",
                params={
                    "q": query,
                    "type_": "Posts",
                    "limit": per_instance,
                    "sort": "TopAll",
                },
                headers={"User-Agent": "MultiSource-AI-Research-Engine/1.0"},
                timeout=8.0,
            )
            if resp.status_code != 200:
                logger.debug(f"Lemmy {instance} returned {resp.status_code}")
                return []
            data = resp.json()
            for post_view in data.get("posts", []):
                post = post_view.get("post", {})
                creator = post_view.get("creator", {})
                counts = post_view.get("counts", {})

                post_id = str(post.get("id", ""))
                title = post.get("name") or "Untitled"
                body = post.get("body") or ""
                ap_id = post.get("ap_id") or f"{instance}/post/{post_id}"
                published_str = post.get("published")
                pub_at: Optional[datetime] = None
                if published_str:
                    try:
                        pub_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                    except Exception:
                        pass
                username = creator.get("name") or creator.get("display_name")
                score = counts.get("score", 0)
                comments = counts.get("comments", 0)
                results.append(RawResult(
                    source_name="lemmy",
                    source_item_id=f"{instance}_{post_id}",
                    title=title,
                    content_snippet=body[:500] if body else None,
                    source_url=ap_id,
                    author=username,
                    published_at=pub_at,
                    content_type="post",
                    engagement_metrics={
                        "score": score,
                        "comments": comments,
                        "upvotes": counts.get("upvotes", 0),
                        "downvotes": counts.get("downvotes", 0),
                    },
                    metadata={
                        "instance": instance,
                        "post_id": post_id,
                        "community": post_view.get("community", {}).get("name"),
                        "nsfw": post.get("nsfw", False),
                    },
                ))
        except Exception as e:
            logger.debug(f"Lemmy {instance} search error: {e}")
        return results

    async def test_connection(self) -> Dict[str, Any]:
        now_str = datetime.now(timezone.utc).isoformat()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{LEMMY_INSTANCES[0]}/api/v3/search",
                    params={"q": "hello", "type_": "Posts", "limit": 1},
                    headers={"User-Agent": "MultiSource-AI-Research-Engine/1.0"},
                )
            if resp.status_code == 200:
                diag = {
                    "configured": True, "authorized": True, "connected": True,
                    "status": "connected",
                    "message": f"Lemmy API reachable via {LEMMY_INSTANCES[0]}",
                    "last_checked_at": now_str,
                }
            else:
                diag = {
                    "configured": True, "authorized": False, "connected": False,
                    "status": "error",
                    "message": f"Lemmy returned HTTP {resp.status_code}",
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
            "message": f"Lemmy public search across {len(LEMMY_INSTANCES)} instances — no auth required",
        }

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        per_instance = max(1, limit // len(LEMMY_INSTANCES))
        async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
            tasks = [
                self._search_instance(client, inst, query, per_instance)
                for inst in LEMMY_INSTANCES
            ]
            groups = await asyncio.gather(*tasks, return_exceptions=True)
        results: List[RawResult] = []
        for group in groups:
            if isinstance(group, list):
                results.extend(group)
        return results[:limit]
