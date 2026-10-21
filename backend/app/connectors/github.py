import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.connectors.base import BaseConnector, RawResult
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class GitHubConnector(BaseConnector):
    source_id = "github"
    name = "GitHub Issues & Repositories"
    category = "developer"
    requires_auth = False
    supported_content_types = ["issue", "repository", "discussion"]

    BASE_URL = "https://api.github.com/search/issues"

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        results: List[RawResult] = []
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "MultiSource-AI-Research-Engine"
        }
        if settings.GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Search issues and PRs related to query
                # E.g. query terms plus state:all
                q = f"{query} state:all"
                params = {
                    "q": q,
                    "per_page": min(limit, 30),
                    "sort": "reactions"
                }
                response = await client.get(self.BASE_URL, params=params, headers=headers)
                
                if response.status_code == 403:
                    logger.warning("GitHub API rate limit exceeded")
                    return results
                elif response.status_code != 200:
                    logger.error(f"GitHub API error {response.status_code}: {response.text}")
                    return results

                data = response.json()
                for item in data.get("items", []):
                    title = item.get("title", "")
                    body = item.get("body", "") or ""
                    # Short snippet of body
                    snippet = (body[:280] + "...") if len(body) > 280 else body
                    
                    pub_str = item.get("created_at")
                    published_at = None
                    if pub_str:
                        try:
                            published_at = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                        except Exception:
                            pass

                    reactions = item.get("reactions", {})
                    engagement = {
                        "comments": item.get("comments", 0),
                        "reactions_total": reactions.get("total_count", 0),
                        "plus_one": reactions.get("+1", 0)
                    }

                    results.append(
                        RawResult(
                            source_name="github",
                            source_item_id=str(item.get("id")),
                            title=title,
                            content_snippet=snippet or f"GitHub issue #{item.get('number')} in {item.get('repository_url', '').split('/')[-1]}",
                            source_url=item.get("html_url", ""),
                            author=item.get("user", {}).get("login"),
                            published_at=published_at,
                            content_type="issue",
                            engagement_metrics=engagement,
                            metadata={
                                "state": item.get("state"),
                                "labels": [l.get("name") for l in item.get("labels", [])]
                            }
                        )
                    )
        except Exception as e:
            logger.error(f"GitHub search failed: {e}")
        return results

    def check_health(self) -> Dict[str, Any]:
        has_token = bool(settings.GITHUB_TOKEN)
        return {
            "status": "operational",
            "auth_status": "configured" if has_token else "not_required (unauthenticated rate limits apply)",
            "message": "GitHub Search API ready (60 req/hr unauth, 5000 req/hr auth)"
        }
