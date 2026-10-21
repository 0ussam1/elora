import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.connectors.base import BaseConnector, RawResult
import logging

logger = logging.getLogger(__name__)

class WikipediaConnector(BaseConnector):
    source_id = "wikipedia"
    name = "Wikipedia Knowledge Base"
    category = "encyclopedia"
    requires_auth = False
    supported_content_types = ["article", "encyclopedic_summary"]

    BASE_URL = "https://en.wikipedia.org/w/api.php"

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        results: List[RawResult] = []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                params = {
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "format": "json",
                    "srlimit": min(limit, 20)
                }
                headers = {"User-Agent": "MultiSource-AI-Research-Engine/1.0"}
                response = await client.get(self.BASE_URL, params=params, headers=headers)
                if response.status_code != 200:
                    return results

                data = response.json()
                search_hits = data.get("query", {}).get("search", [])

                for hit in search_hits:
                    title = hit.get("title", "")
                    page_id = hit.get("pageid")
                    snippet_html = hit.get("snippet", "")

                    import re
                    snippet = re.sub(r'<[^>]+>', '', snippet_html)
                    url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"

                    pub_str = hit.get("timestamp")
                    published_at = None
                    if pub_str:
                        try:
                            published_at = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                        except Exception:
                            pass

                    results.append(
                        RawResult(
                            source_name="wikipedia",
                            source_item_id=str(page_id),
                            title=title,
                            content_snippet=snippet,
                            source_url=url,
                            author="Wikipedia Contributors",
                            published_at=published_at,
                            content_type="article",
                            engagement_metrics={"wordcount": hit.get("wordcount", 0)},
                            metadata={"pageid": page_id}
                        )
                    )
        except Exception as e:
            logger.error(f"Wikipedia search failed: {e}")
        return results

    def check_health(self) -> Dict[str, Any]:
        return {
            "status": "operational",
            "auth_status": "not_required",
            "message": "Wikipedia Action API operational"
        }
