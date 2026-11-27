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
                if response.status_code == 200:
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
                else:
                    logger.warning(f"DuckDuckGo returned status {response.status_code} (bot challenge or rate limit). Falling back to Open Web / Wikipedia search.")

                # Fallback to Wikipedia search if DuckDuckGo yielded 0 results or blocked
                if not results:
                    wiki_results = await self._fallback_wikipedia_search(client, query, limit)
                    results.extend(wiki_results)
        except Exception as e:
            logger.error(f"WebSearchConnector failed: {e}")
        return results

    async def _fallback_wikipedia_search(self, client: httpx.AsyncClient, query: str, limit: int) -> List[RawResult]:
        """Fallback to Wikipedia Open Web search when DuckDuckGo presents anti-bot challenge."""
        fallback_results: List[RawResult] = []
        try:
            resp = await client.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": min(limit, 20),
                    "format": "json",
                },
                headers={"User-Agent": "ELORA-Research-Engine/1.0 (academic/open-source; contact: researcher@example.com)"},
                timeout=8.0,
            )
            if resp.status_code == 200:
                import re
                items = resp.json().get("query", {}).get("search", [])
                for item in items:
                    title = item.get("title", "")
                    page_id = item.get("pageid", "")
                    raw_snippet = item.get("snippet", "")
                    clean_snippet = re.sub(r"<[^>]+>", "", raw_snippet).strip()
                    url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
                    pub_str = item.get("timestamp")
                    pub_at = None
                    if pub_str:
                        try:
                            pub_at = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                        except Exception:
                            pass
                    fallback_results.append(
                        RawResult(
                            source_name="web_search",
                            source_item_id=str(page_id) if page_id else url,
                            title=title,
                            content_snippet=clean_snippet,
                            source_url=url,
                            author="Wikipedia Contributors",
                            published_at=pub_at,
                            content_type="article",
                            engagement_metrics={"wordcount": item.get("wordcount", 0)},
                            metadata={"search_engine": "duckduckgo_fallback_wikipedia", "pageid": page_id}
                        )
                    )
        except Exception as e:
            logger.warning(f"Wikipedia fallback web search error: {e}")
        return fallback_results

    def check_health(self) -> Dict[str, Any]:
        return {
            "status": "operational",
            "auth_status": "not_required",
            "message": "DuckDuckGo Web Search endpoint accessible"
        }
