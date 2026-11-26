"""
NARA National Archives Catalog Connector
=========================================
Source: https://catalog.archives.gov/
API: Official REST API v2 — https://catalog.archives.gov/api/v2/records/search
Auth: Requires a free API key (email Catalog_API@nara.gov to request one).
      Without a key the connector returns a not_configured status gracefully.
Content: US federal government archival records — textual records, photographs,
         moving images, sound recordings, electronic records, maps, and more.
         Covers all federal agencies from founding to present.
Rate: 10,000 queries/month per key (free tier).
"""
import httpx
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.connectors.base import BaseConnector, RawResult
from app.core.config import settings

logger = logging.getLogger(__name__)


class NARAConnector(BaseConnector):
    """
    National Archives (NARA) Catalog API v2.
    Official REST API — requires a free API key from NARA.
    Returns federal archival records with full metadata, digital object links,
    OCR text, and original document provenance.
    """
    source_id = "nara"
    name = "National Archives (NARA)"
    category = "intelligence_archives"
    requires_auth = True
    supported_content_types = ["document", "archival_record", "declassified_record"]

    BASE_URL = "https://catalog.archives.gov/api/v2/records/search"
    RECORD_URL = "https://catalog.archives.gov/id/{naId}"

    def __init__(self):
        self._last_diagnostic: Optional[Dict[str, Any]] = None

    @property
    def rate_limit_per_minute(self) -> int:
        return 20  # Conservative within 10K/month free tier

    def is_configured(self) -> bool:
        return bool(settings.NARA_API_KEY)

    def _headers(self) -> Dict[str, str]:
        return {
            "x-api-key": settings.NARA_API_KEY or "",
            "Content-Type": "application/json",
            "User-Agent": "ELORA-Research-Engine/1.0 (academic/open-source; contact: researcher@example.com)",
        }

    async def test_connection(self) -> Dict[str, Any]:
        now_str = datetime.now(timezone.utc).isoformat()
        if not self.is_configured():
            diag = {
                "configured": False, "authorized": False, "connected": False,
                "status": "not_configured",
                "message": (
                    "Missing NARA_API_KEY in .env. "
                    "Request a free key by emailing Catalog_API@nara.gov. "
                    "See: https://www.archives.gov/research/catalog/help/api"
                ),
                "last_checked_at": now_str,
            }
            self._last_diagnostic = diag
            return diag
        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.get(
                    self.BASE_URL,
                    headers=self._headers(),
                    params={"q": "declassified", "limit": 1, "availableOnline": "true"},
                )
            if resp.status_code == 200:
                diag = {
                    "configured": True, "authorized": True, "connected": True,
                    "status": "connected",
                    "message": "NARA Catalog API authenticated and reachable",
                    "last_checked_at": now_str,
                }
            elif resp.status_code in (401, 403):
                diag = {
                    "configured": True, "authorized": False, "connected": False,
                    "status": "pending_authorization",
                    "message": f"NARA API key rejected (HTTP {resp.status_code}). Verify NARA_API_KEY.",
                    "last_checked_at": now_str,
                }
            elif resp.status_code == 429:
                diag = {
                    "configured": True, "authorized": True, "connected": False,
                    "status": "rate_limited",
                    "message": "NARA API quota exceeded (10,000 queries/month on free tier).",
                    "last_checked_at": now_str,
                }
            else:
                diag = {
                    "configured": True, "authorized": False, "connected": False,
                    "status": "error",
                    "message": f"NARA API returned HTTP {resp.status_code}: {resp.text[:200]}",
                    "last_checked_at": now_str,
                }
        except Exception as e:
            diag = {
                "configured": self.is_configured(), "authorized": False, "connected": False,
                "status": "error",
                "message": f"Network error connecting to NARA API: {e}",
                "last_checked_at": now_str,
            }
        self._last_diagnostic = diag
        return diag

    def check_health(self) -> Dict[str, Any]:
        if not self.is_configured():
            return {
                "status": "not_configured",
                "auth_status": "not_configured",
                "message": (
                    "Missing NARA_API_KEY — request free at: "
                    "email Catalog_API@nara.gov | "
                    "docs: https://www.archives.gov/research/catalog/help/api"
                ),
            }
        if self._last_diagnostic:
            return {
                "status": self._last_diagnostic.get("status", "configured"),
                "auth_status": "authorized" if self._last_diagnostic.get("authorized") else self._last_diagnostic.get("status"),
                "message": self._last_diagnostic.get("message", ""),
            }
        return {
            "status": "configured",
            "auth_status": "configured",
            "message": "NARA API key present — 10,000 free queries/month",
        }

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        if not self.is_configured():
            logger.info("NARA search skipped: NARA_API_KEY not configured")
            return []

        results: List[RawResult] = []
        params: Dict[str, Any] = {
            "q": query,
            "limit": min(limit, 100),
            "availableOnline": "true",  # Only return records with digital objects
            "resultFields": (
                "naId,title,description,creator,date,dateQualifier,"
                "accessRestrictionStatus,useRestrictionStatus,"
                "specificRecordsType,holdingsMeasurements,digitalObjects"
            ),
        }

        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.get(self.BASE_URL, headers=self._headers(), params=params)

            if resp.status_code != 200:
                logger.warning(f"NARA search returned {resp.status_code}: {resp.text[:300]}")
                return []

            data = resp.json()
            hits = data.get("body", {}).get("hits", {}).get("hits", [])
            if not hits:
                # Try alternate response structure
                hits = data.get("results", [])

            for hit in hits:
                src = hit.get("_source", hit)
                na_id = str(src.get("naId", ""))
                title = src.get("title", {})
                if isinstance(title, dict):
                    title = title.get("value", "") or title.get("label", "")
                title = str(title) or "NARA Archival Record"

                desc = src.get("description", {})
                if isinstance(desc, dict):
                    desc = desc.get("value", "") or desc.get("label", "")
                snippet = str(desc)[:500] if desc else None

                # Creator / contributor
                creator = src.get("creator", {})
                if isinstance(creator, list) and creator:
                    creator = creator[0]
                if isinstance(creator, dict):
                    creator = creator.get("name", "") or creator.get("termName", "")
                author = str(creator) if creator else None

                # Date
                date_val = src.get("date") or src.get("coverageDates")
                pub_at: Optional[datetime] = None
                if isinstance(date_val, str) and date_val:
                    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y"):
                        try:
                            pub_at = datetime.strptime(date_val[:10], fmt).replace(tzinfo=timezone.utc)
                            break
                        except ValueError:
                            pass

                # URL — prefer digital object URL, else catalog page
                digital_objs = src.get("digitalObjects", [])
                doc_url = None
                if isinstance(digital_objs, list) and digital_objs:
                    doc_url = digital_objs[0].get("objectUrl") if isinstance(digital_objs[0], dict) else None
                catalog_url = self.RECORD_URL.format(naId=na_id) if na_id else "https://catalog.archives.gov"
                url = doc_url or catalog_url

                access_restriction = src.get("accessRestrictionStatus", "")
                use_restriction = src.get("useRestrictionStatus", "")
                record_type = src.get("specificRecordsType", "")

                results.append(RawResult(
                    source_name="nara",
                    source_item_id=na_id,
                    title=title,
                    content_snippet=snippet,
                    source_url=url,
                    author=author,
                    published_at=pub_at,
                    content_type="archival_record",
                    engagement_metrics={},
                    metadata={
                        "agency": "NARA",
                        "archive": "National Archives Catalog",
                        "nara_id": na_id,
                        "catalog_url": catalog_url,
                        "document_type": record_type or "archival_record",
                        "access_restriction": access_restriction,
                        "use_restriction": use_restriction,
                        "has_digital_object": bool(digital_objs),
                        "is_pdf": bool(doc_url and doc_url.lower().endswith(".pdf")),
                        "classification_status": (
                            "restricted" if access_restriction else "unrestricted"
                        ),
                    },
                ))
        except Exception as e:
            logger.error(f"NARA search failed: {e}")
        return results
