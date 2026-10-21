import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.connectors.base import BaseConnector, RawResult
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class StackExchangeConnector(BaseConnector):
    source_id = "stackexchange"
    name = "Stack Overflow / Stack Exchange"
    category = "developer"
    requires_auth = False
    supported_content_types = ["question", "answer"]

    BASE_URL = "https://api.stackexchange.com/2.3/search/advanced"

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        results: List[RawResult] = []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                params = {
                    "order": "desc",
                    "sort": "relevance",
                    "q": query,
                    "site": "stackoverflow",
                    "pagesize": min(limit, 30),
                    "filter": "withbody"
                }
                if settings.STACKEXCHANGE_KEY:
                    params["key"] = settings.STACKEXCHANGE_KEY

                response = await client.get(self.BASE_URL, params=params)
                if response.status_code != 200:
                    logger.warning(f"StackExchange API returned {response.status_code}: {response.text}")
                    return results

                data = response.json()
                for item in data.get("items", []):
                    title = item.get("title", "")
                    body = item.get("body", "") or ""
                    
                    # Basic strip html tag for snippet
                    import re
                    clean_body = re.sub(r'<[^>]+>', '', body)
                    snippet = (clean_body[:280] + "...") if len(clean_body) > 280 else clean_body

                    creation_date = item.get("creation_date")
                    published_at = datetime.fromtimestamp(creation_date) if creation_date else None

                    engagement = {
                        "score": item.get("score", 0),
                        "answer_count": item.get("answer_count", 0),
                        "view_count": item.get("view_count", 0),
                        "is_answered": item.get("is_answered", False)
                    }

                    results.append(
                        RawResult(
                            source_name="stackexchange",
                            source_item_id=str(item.get("question_id")),
                            title=title,
                            content_snippet=snippet,
                            source_url=item.get("link", ""),
                            author=item.get("owner", {}).get("display_name"),
                            published_at=published_at,
                            content_type="question",
                            engagement_metrics=engagement,
                            metadata={"tags": item.get("tags", [])}
                        )
                    )
        except Exception as e:
            logger.error(f"StackExchange search failed: {e}")
        return results

    def check_health(self) -> Dict[str, Any]:
        has_key = bool(settings.STACKEXCHANGE_KEY)
        return {
            "status": "operational",
            "auth_status": "configured" if has_key else "not_required (300 req/day without key)",
            "message": "StackExchange 2.3 public API operational"
        }
