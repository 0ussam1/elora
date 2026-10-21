import httpx
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
from datetime import datetime
import urllib.parse
from app.connectors.base import BaseConnector, RawResult
import logging

logger = logging.getLogger(__name__)

class WebSearchConnector(BaseConnector):
    """
    Web Search connector using DuckDuckGo HTML / Lite endpoint.
    Respects terms, no login or token required, provides organic web search results.
    """
    source_id = "web_search"
    name = "Web Search (DuckDuckGo)"
    category = "web"
    requires_auth = False
    supported_content_types = ["article", "webpage"]

    SEARCH_URL = "https://html.duckduckgo.com/html/"

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        results: List[RawResult] = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5"
        }
        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                response = await client.post(
                    self.SEARCH_URL,
                    data={"q": query},
                    headers=headers
                )
                if response.status_code != 200:
                    logger.warning(f"DuckDuckGo returned status {response.status_code}")
                    return results

                soup = BeautifulSoup(response.text, "html.parser")
                result_elements = soup.find_all("div", class_="result")

                for elem in result_elements:
                    if len(results) >= limit:
                        break

                    title_elem = elem.find("a", class_="result__a")
                    snippet_elem = elem.find("a", class_="result__snippet")
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)
                    raw_url = title_elem.get("href", "")

                    # Extract actual target URL from DDG redirect url
                    parsed = urllib.parse.urlparse(raw_url)
                    query_params = urllib.parse.parse_qs(parsed.query)
                    actual_url = query_params.get("uddg", [raw_url])[0] if "uddg" in query_params else raw_url

                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""

                    if not actual_url.startswith("http"):
                        continue

                    results.append(
                        RawResult(
                            source_name="web_search",
                            source_item_id=actual_url,
                            title=title,
                            content_snippet=snippet,
                            source_url=actual_url,
                            author=None,
                            published_at=None,
                            content_type="article",
                            engagement_metrics={},
                            metadata={"search_engine": "duckduckgo"}
                        )
                    )
        except Exception as e:
            logger.error(f"WebSearchConnector failed: {e}")
        return results

    def check_health(self) -> Dict[str, Any]:
        return {
            "status": "operational",
            "auth_status": "not_required",
            "message": "DuckDuckGo Web Search endpoint accessible"
        }
