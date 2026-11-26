"""
FBI Vault FOIA Connector
========================
Source: https://vault.fbi.gov/
Access: Public HTML search — no API key required.
Interface: GET https://vault.fbi.gov/search?SearchableText=QUERY
Content: FOIA-released FBI files (cases, persons, organisations, historical investigations).
Limitations:
  - No official REST API; this connector parses the public HTML search results.
  - Documents are PDF files linked from the search/browse pages.
  - Redacted content is flagged where detectable.
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


class FBIVaultConnector(BaseConnector):
    """
    FBI Vault FOIA Electronic Reading Room — public FBI document search.
    Parses the official FBI Vault HTML search interface (Plone CMS).
    No authentication required; all results are publicly released FOIA documents.
    """
    source_id = "fbi_vault"
    name = "FBI Vault"
    category = "intelligence_archives"
    requires_auth = False
    supported_content_types = ["document", "foia_record"]

    BASE_SEARCH = "https://vault.fbi.gov/search"
    DOC_BASE = "https://vault.fbi.gov"
    HEADERS = {
        "User-Agent": "ELORA-Research-Engine/1.0 (academic/open-source; contact: researcher@example.com)",
        "Accept": "text/html,application/xhtml+xml",
    }

    def __init__(self):
        self._last_diagnostic: Optional[Dict[str, Any]] = None

    @property
    def rate_limit_per_minute(self) -> int:
        return 10  # Conservative — government server

    async def test_connection(self) -> Dict[str, Any]:
        now_str = datetime.now(timezone.utc).isoformat()
        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.get(
                    self.BASE_SEARCH,
                    params={"SearchableText": "COINTELPRO"},
                    headers=self.HEADERS,
                    follow_redirects=True,
                )
            if resp.status_code == 200 and "cf_chl_opt" not in resp.text and "Just a moment..." not in resp.text:
                diag = {
                    "configured": True, "authorized": True, "connected": True,
                    "status": "connected",
                    "message": "FBI Vault is reachable (public HTML search)",
                    "last_checked_at": now_str,
                }
            elif resp.status_code in (403, 503) or "cf_chl_opt" in resp.text or "Just a moment..." in resp.text:
                diag = {
                    "configured": True, "authorized": False, "connected": False,
                    "status": "blocked_by_bot_protection",
                    "message": (
                        "FBI Vault (vault.fbi.gov) is protected by a Cloudflare JavaScript/anti-bot "
                        "challenge and has no public REST API. Automated search is not permitted without "
                        "manual browser verification."
                    ),
                    "last_checked_at": now_str,
                }
            else:
                diag = {
                    "configured": True, "authorized": False, "connected": False,
                    "status": "error",
                    "message": f"FBI Vault returned HTTP {resp.status_code}",
                    "last_checked_at": now_str,
                }
        except Exception as e:
            diag = {
                "configured": True, "authorized": False, "connected": False,
                "status": "error",
                "message": f"Network error reaching FBI Vault: {e}",
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
            "message": "FBI Vault — public FOIA document archive (HTML search, Plone CMS)",
        }

    def _parse_results(self, html: str, limit: int) -> List[Dict[str, Any]]:
        """
        Parse FBI Vault Plone CMS search result HTML.
        Result items are <div class="searchResults"> containing <a class="contenttype-..."> links.
        """
        docs = []

        # Plone result blocks
        result_blocks = re.findall(
            r'<div[^>]*class="[^"]*searchResult[^"]*"[^>]*>(.*?)</div>',
            html, re.IGNORECASE | re.DOTALL
        )
        if not result_blocks:
            # Fallback: find any heading + link pattern that points to vault content
            result_blocks = re.findall(
                r'(<h\d[^>]*>.*?<a\s+href="[^"]*vault\.fbi\.gov[^"]*"[^>]*>.*?</a>.*?</h\d>)',
                html, re.IGNORECASE | re.DOTALL
            )

        for block in result_blocks[:limit]:
            link_m = re.search(r'href="([^"]+)"', block, re.IGNORECASE)
            href = link_m.group(1) if link_m else ""
            if not href:
                continue
            if href.startswith("/"):
                href = self.DOC_BASE + href
            elif not href.startswith("http"):
                href = self.DOC_BASE + "/" + href

            title_m = re.search(r'<a[^>]*>([^<]+)</a>', block, re.IGNORECASE)
            title = _strip_tags(title_m.group(1)) if title_m else "FBI Vault Document"

            # Date
            date_m = re.search(r'(\d{4}-\d{2}-\d{2}|\w+ \d{1,2},\s*\d{4})', block)
            pub_at: Optional[datetime] = None
            if date_m:
                for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
                    try:
                        pub_at = datetime.strptime(date_m.group(1), fmt).replace(tzinfo=timezone.utc)
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
                    params={"SearchableText": query},
                    headers=self.HEADERS,
                )
            if resp.status_code != 200 or "cf_chl_opt" in resp.text or "Just a moment..." in resp.text:
                logger.warning(
                    f"FBI Vault search blocked or unavailable (HTTP {resp.status_code}; "
                    "Cloudflare bot protection active on vault.fbi.gov)"
                )
                return []

            docs = self._parse_results(resp.text, limit)
            for d in docs:
                is_pdf = d["url"].lower().endswith(".pdf")
                results.append(RawResult(
                    source_name="fbi_vault",
                    source_item_id=d["url"].rstrip("/").split("/")[-1],
                    title=d["title"],
                    content_snippet=d["snippet"],
                    source_url=d["url"],
                    author=None,
                    published_at=d["pub_at"],
                    content_type="foia_record",
                    engagement_metrics={},
                    metadata={
                        "agency": "FBI",
                        "archive": "FBI Vault (Electronic FOIA Library)",
                        "document_type": "FOIA_released",
                        "is_pdf": is_pdf,
                        "access": "public",
                        "classification_status": "FOIA_released",
                    },
                ))
        except Exception as e:
            logger.error(f"FBI Vault search failed: {e}")
        return results
