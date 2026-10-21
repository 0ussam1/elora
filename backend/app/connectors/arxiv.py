import httpx
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.connectors.base import BaseConnector, RawResult
import logging

logger = logging.getLogger(__name__)

class ArxivConnector(BaseConnector):
    source_id = "arxiv"
    name = "arXiv Academic Papers"
    category = "academic"
    requires_auth = False
    supported_content_types = ["paper", "preprint"]

    BASE_URL = "http://export.arxiv.org/api/query"

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        results: List[RawResult] = []
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                params = {
                    "search_query": f"all:{query}",
                    "start": 0,
                    "max_results": min(limit, 30),
                    "sortBy": "relevance",
                    "sortOrder": "descending"
                }
                response = await client.get(self.BASE_URL, params=params)
                if response.status_code != 200:
                    logger.warning(f"arXiv API returned {response.status_code}")
                    return results

                # Parse Atom XML
                root = ET.fromstring(response.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}

                for entry in root.findall("atom:entry", ns):
                    title_elem = entry.find("atom:title", ns)
                    summary_elem = entry.find("atom:summary", ns)
                    id_elem = entry.find("atom:id", ns)
                    published_elem = entry.find("atom:published", ns)
                    author_elem = entry.find("atom:author/atom:name", ns)

                    title = title_elem.text.strip().replace("\n", " ") if title_elem is not None and title_elem.text else ""
                    summary = summary_elem.text.strip().replace("\n", " ") if summary_elem is not None and summary_elem.text else ""
                    source_url = id_elem.text.strip() if id_elem is not None and id_elem.text else ""
                    author = author_elem.text.strip() if author_elem is not None and author_elem.text else None

                    published_at = None
                    if published_elem is not None and published_elem.text:
                        try:
                            published_at = datetime.fromisoformat(published_elem.text.replace("Z", "+00:00"))
                        except Exception:
                            pass

                    results.append(
                        RawResult(
                            source_name="arxiv",
                            source_item_id=source_url.split("/")[-1] if source_url else None,
                            title=title,
                            content_snippet=(summary[:300] + "...") if len(summary) > 300 else summary,
                            source_url=source_url,
                            author=author,
                            published_at=published_at,
                            content_type="paper",
                            engagement_metrics={},
                            metadata={"full_summary_length": len(summary)}
                        )
                    )
        except Exception as e:
            logger.error(f"arXiv search failed: {e}")
        return results

    def check_health(self) -> Dict[str, Any]:
        return {
            "status": "operational",
            "auth_status": "not_required",
            "message": "arXiv public API operational"
        }
