import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.connectors.base import BaseConnector, RawResult
import logging

logger = logging.getLogger(__name__)

class HackerNewsConnector(BaseConnector):
    source_id = "hackernews"
    name = "Hacker News (Algolia API)"
    category = "community"
    requires_auth = False
    supported_content_types = ["discussion", "story", "comment"]

    BASE_URL = "https://hn.algolia.com/api/v1/search"

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        results: List[RawResult] = []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                params = {
                    "query": query,
                    "hitsPerPage": min(limit, 50),
                    "tags": "(story,poll)"
                }
                response = await client.get(self.BASE_URL, params=params)
                if response.status_code != 200:
                    logger.error(f"Hacker News API error {response.status_code}: {response.text}")
                    return results

                data = response.json()
                for hit in data.get("hits", []):
                    title = hit.get("title") or hit.get("story_title")
                    if not title:
                        continue

                    # Direct story URL or HN discussion item URL
                    object_id = hit.get("objectID")
                    hn_item_url = f"https://news.ycombinator.com/item?id={object_id}"
                    source_url = hit.get("url") or hn_item_url

                    # Published at parsing
                    pub_str = hit.get("created_at")
                    published_at = None
                    if pub_str:
                        try:
                            published_at = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                        except Exception:
                            pass

                    # Engagement metrics
                    engagement = {
                        "points": hit.get("points") or 0,
                        "comments_count": hit.get("num_comments") or 0
                    }

                    results.append(
                        RawResult(
                            source_name="hackernews",
                            source_item_id=str(object_id),
                            title=title.strip(),
                            content_snippet=hit.get("story_text") or f"Discussion on Hacker News with {hit.get('points', 0)} points and {hit.get('num_comments', 0)} comments.",
                            source_url=source_url,
                            author=hit.get("author"),
                            published_at=published_at,
                            content_type="discussion",
                            engagement_metrics=engagement,
                            metadata={"hn_url": hn_item_url, "points": hit.get("points")}
                        )
                    )
        except Exception as e:
            logger.error(f"HackerNews search failed: {e}")
        return results

    def check_health(self) -> Dict[str, Any]:
        return {
            "status": "operational",
            "auth_status": "not_required",
            "message": "Official Algolia HN Search API active"
        }
