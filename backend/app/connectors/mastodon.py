import httpx
import asyncio
import re
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.connectors.base import BaseConnector, RawResult
from app.core.config import settings

logger = logging.getLogger(__name__)

# Curated list of large public Mastodon instances
MASTODON_INSTANCES = [
    "https://mastodon.social",
    "https://fosstodon.org",
    "https://hachyderm.io",
]

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Remove HTML tags from Mastodon post content."""
    cleaned = _HTML_TAG_RE.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


class MastodonConnector(BaseConnector):
    """
    Mastodon Social Network Connector.
    Searches multiple public Mastodon instances using the official Mastodon API v2.
    No authentication required for public status search.
    """
    source_id = "mastodon"
    name = "Mastodon"
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
                f"{instance}/api/v2/search",
                params={"q": query, "type": "statuses", "limit": per_instance},
                headers={"User-Agent": "MultiSource-AI-Research-Engine/1.0"},
                timeout=8.0,
            )
            if resp.status_code != 200:
                logger.debug(f"Mastodon {instance} returned {resp.status_code}")
                return []
            data = resp.json()
            for status in data.get("statuses", []):
                status_id = str(status.get("id", ""))
                raw_content = status.get("content") or ""
                content_text = _strip_html(raw_content)
                url = status.get("url") or status.get("uri") or f"{instance}/web/statuses/{status_id}"
                created_at_str = status.get("created_at")
                pub_at: Optional[datetime] = None
                if created_at_str:
                    try:
                        pub_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                    except Exception:
                        pass
                account = status.get("account") or {}
                username = account.get("acct") or account.get("username")
                reblogs = status.get("reblogs_count", 0)
                favourites = status.get("favourites_count", 0)
                replies = status.get("replies_count", 0)
                # Build a meaningful title from the first line or first 80 chars
                title = content_text[:80].strip()
                if not title:
                    title = f"Mastodon post by @{username}"
                tags = [t.get("name", "") for t in (status.get("tags") or [])]
                results.append(RawResult(
                    source_name="mastodon",
                    source_item_id=f"{instance}_{status_id}",
                    title=title,
                    content_snippet=content_text[:500] if content_text else None,
                    source_url=url,
                    author=username,
                    published_at=pub_at,
                    content_type="post",
                    engagement_metrics={
                        "reblogs_count": reblogs,
                        "favourites_count": favourites,
                        "replies_count": replies,
                    },
                    metadata={
                        "instance": instance,
                        "status_id": status_id,
                        "tags": tags,
                        "language": status.get("language"),
                        "sensitive": status.get("sensitive", False),
                    },
                ))
        except Exception as e:
            logger.debug(f"Mastodon {instance} search error: {e}")
        return results

    async def test_connection(self) -> Dict[str, Any]:
        now_str = datetime.now(timezone.utc).isoformat()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{MASTODON_INSTANCES[0]}/api/v2/search",
                    params={"q": "hello", "type": "statuses", "limit": 1},
                    headers={"User-Agent": "MultiSource-AI-Research-Engine/1.0"},
                )
            if resp.status_code == 200:
                diag = {
                    "configured": True, "authorized": True, "connected": True,
                    "status": "connected",
                    "message": f"Mastodon API reachable via {MASTODON_INSTANCES[0]}",
                    "last_checked_at": now_str,
                }
            else:
                diag = {
                    "configured": True, "authorized": False, "connected": False,
                    "status": "error",
                    "message": f"Mastodon returned HTTP {resp.status_code}",
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
            "message": f"Mastodon public search across {len(MASTODON_INSTANCES)} instances — no auth required",
        }

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        per_instance = max(1, limit // len(MASTODON_INSTANCES))
        async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
            tasks = [
                self._search_instance(client, inst, query, per_instance)
                for inst in MASTODON_INSTANCES
            ]
            groups = await asyncio.gather(*tasks, return_exceptions=True)
        results: List[RawResult] = []
        for group in groups:
            if isinstance(group, list):
                results.extend(group)
        return results[:limit]
