"""
National Security Archive (George Washington University) Connector
==================================================================
Source: https://nsarchive.gwu.edu/
Access: Public HTML search — no API key required.
Interface: GET https://nsarchive.gwu.edu/search?query=QUERY
Content: Declassified and FOIA-released US government documents published by
         GWU's independent NSA research institute — briefing books, document sets,
         investigative compilations, and historical collections.
Limitations:
  - No official REST API; this connector parses the public HTML search interface.
  - Full document PDFs are hosted on nsarchive.gwu.edu and third-party archives.
  - The Digital NSA (DNSA) deep collection requires ProQuest institutional subscription.
  - Only free public briefing books and document sets are retrieved here.
"""
import httpx
import re
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.connectors.base import BaseConnector, RawResult
from app.core.config import settings

logger = logging.getLogger(__name__)

_STRIP_RE = re.compile(r'<[^>]+>')


def _strip_tags(html: str) -> str:
    return re.sub(r'\s+', ' ', _STRIP_RE.sub(' ', html)).strip()


class NatSecArchiveConnector(BaseConnector):
    """
    National Security Archive (GWU) — public declassified document search.
    Parses the public HTML search interface at nsarchive.gwu.edu.
    No authentication required. Only freely accessible briefing books are retrieved.
    """
    source_id = "nat_sec_archive"
    name = "National Security Archive"
    category = "intelligence_archives"
    requires_auth = False
    supported_content_types = ["document", "declassified_record", "briefing_book"]

    BASE_SEARCH = "https://nsarchive.gwu.edu/search"
    BASE_URL = "https://nsarchive.gwu.edu"
    HEADERS = {
        "User-Agent": "ELORA-Research-Engine/1.0 (academic/open-source; contact: researcher@example.com)",
        "Accept": "text/html,application/xhtml+xml",
    }

    def __init__(self):
        self._last_diagnostic: Optional[Dict[str, Any]] = None

    @property
    def rate_limit_per_minute(self) -> int:
        return 10

    async def test_connection(self) -> Dict[str, Any]:
        now_str = datetime.now(timezone.utc).isoformat()
        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.get(
                    self.BASE_SEARCH,
                    params={"query": "declassified"},
                    headers=self.HEADERS,
                    follow_redirects=True,
                )
            if resp.status_code == 200:
                diag = {
                    "configured": True, "authorized": True, "connected": True,
                    "status": "connected",
                    "message": "National Security Archive (GWU) is reachable (public HTML search)",
                    "last_checked_at": now_str,
                }
            else:
                diag = {
                    "configured": True, "authorized": False, "connected": False,
                    "status": "error",
                    "message": f"NSA Archive (GWU) returned HTTP {resp.status_code}",
                    "last_checked_at": now_str,
                }
        except Exception as e:
            diag = {
                "configured": True, "authorized": False, "connected": False,
                "status": "error",
                "message": f"Network error reaching NSA Archive (GWU): {e}",
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
            "message": "National Security Archive (GWU) — public declassified document search. Deep DNSA collection requires ProQuest subscription.",
        }

    def _parse_results(self, html: str, limit: int) -> List[Dict[str, Any]]:
        """Parse GWU NSA search result HTML."""
        docs = []

        # GWU Drupal: search results typically in <article> or <div class="views-row"> blocks
        blocks = re.findall(
            r'<article[^>]*>(.*?)</article>',
            html, re.IGNORECASE | re.DOTALL
        )
        if not blocks:
            blocks = re.findall(
                r'<div[^>]*class="[^"]*views-row[^"]*"[^>]*>(.*?)</div>\s*(?=<div[^>]*class="[^"]*views-row|$)',
                html, re.IGNORECASE | re.DOTALL
            )
        if not blocks:
            # Last resort: grab all internal links with meaningful text
            blocks = re.findall(
                r'<a\s+href="(/[^"]*(?:briefing-book|document|collection|publication)[^"]*)"[^>]*>([^<]{10,})</a>',
                html, re.IGNORECASE
            )
            for href, title_text in blocks[:limit]:
                url = self.BASE_URL + href
                docs.append({"title": _strip_tags(title_text), "url": url, "pub_at": None, "snippet": None})
            return docs

        for block in blocks[:limit]:
            link_m = re.search(r'href="([^"]+)"', block, re.IGNORECASE)
            href = link_m.group(1) if link_m else ""
            if not href:
                continue
            if href.startswith("/"):
                href = self.BASE_URL + href
            elif not href.startswith("http"):
                continue

            title_m = re.search(r'<(?:h[1-6]|a)[^>]*>([^<]{5,})</(?:h[1-6]|a)>', block, re.IGNORECASE)
            title = _strip_tags(title_m.group(1)) if title_m else "NSA Archive Document"

            date_m = re.search(r'(\d{4}-\d{2}-\d{2}|\w+ \d{1,2},\s*\d{4}|\d{4})', block)
            pub_at: Optional[datetime] = None
            if date_m:
                val = date_m.group(1)
                for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%Y"):
                    try:
                        pub_at = datetime.strptime(val, fmt).replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        pass

            snippet_m = re.search(r'<p[^>]*>(.*?)</p>', block, re.IGNORECASE | re.DOTALL)
            snippet = _strip_tags(snippet_m.group(1))[:500] if snippet_m else None

            docs.append({"title": title, "url": href, "pub_at": pub_at, "snippet": snippet})

        return docs

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        results: List[RawResult] = []
        try:
            async with httpx.AsyncClient(
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
                follow_redirects=True,
            ) as client:
                resp = await client.get(
                    self.BASE_SEARCH,
                    params={"query": query},
                    headers=self.HEADERS,
                )
            if resp.status_code != 200:
                logger.warning(f"NSA Archive (GWU) search returned {resp.status_code}")
                return []

            docs = self._parse_results(resp.text, limit)
            for d in docs:
                is_pdf = d["url"].lower().endswith(".pdf")
                is_briefing = "briefing-book" in d["url"] or "briefing_book" in d["url"]
                content_type = "briefing_book" if is_briefing else ("document" if is_pdf else "declassified_record")
                results.append(RawResult(
                    source_name="nat_sec_archive",
                    source_item_id=d["url"].rstrip("/").split("/")[-1],
                    title=d["title"],
                    content_snippet=d["snippet"],
                    source_url=d["url"],
                    author=None,
                    published_at=d["pub_at"],
                    content_type=content_type,
                    engagement_metrics={},
                    metadata={
                        "agency": "Various / US Government",
                        "archive": "National Security Archive (GWU)",
                        "document_type": "FOIA_released" if is_pdf else "briefing_book",
                        "is_pdf": is_pdf,
                        "access": "public",
                        "classification_status": "declassified",
                        "note": "Deep DNSA collection requires ProQuest subscription. Only free public materials retrieved.",
                    },
                ))
        except Exception as e:
            logger.error(f"NSA Archive (GWU) search failed: {e}")
        return results
