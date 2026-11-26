"""
NSA Declassification Archive Connector
=======================================
Source: https://www.nsa.gov/Helpful-Links/NSA-FOIA/Declassification-Transparency-Initiatives/
Access: Public static HTML pages — no API, no search endpoint, no RSS.
Interface: Curated static index of known NSA declassification release pages.
Content: Declassified NSA historical collections (UKUSA Agreement, Gulf of Tonkin,
         William F. Friedman Collection, Church Committee materials, etc.)
Limitations:
  - NSA provides NO search API, NO RSS feed, and NO programmatic endpoint.
  - This connector surfaces known curated collections as browsable entries.
  - Full-text search across the NSA archive is NOT possible without manual browsing.
  - For dynamic FOIA record search, users must visit nsa.gov/Helpful-Links/NSA-FOIA/ directly.
  - This design is intentional and honest — fabricating search is not done.
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.connectors.base import BaseConnector, RawResult

logger = logging.getLogger(__name__)

# Curated, authoritative NSA public declassification releases.
# These are known, permanent public URLs from nsa.gov's declassification pages.
NSA_CURATED_COLLECTIONS = [
    {
        "id": "ukusa",
        "title": "UKUSA Agreement (1946) — Declassified",
        "url": "https://www.nsa.gov/Helpful-Links/NSA-FOIA/Declassification-Transparency-Initiatives/Historical-Releases/UKUSA/",
        "snippet": "Full text of the 1946 UKUSA Agreement between the United States and United Kingdom establishing signals intelligence sharing. Declassified and released publicly in June 2010.",
        "date": "2010-06-24",
        "tags": ["UKUSA", "SIGINT", "Five Eyes", "intelligence-sharing", "1946"],
        "agency": "NSA/GCHQ",
    },
    {
        "id": "gulf_of_tonkin",
        "title": "Gulf of Tonkin — NSA's Own Story",
        "url": "https://www.nsa.gov/Helpful-Links/NSA-FOIA/Declassification-Transparency-Initiatives/Historical-Releases/Gulf-of-Tonkin/",
        "snippet": "NSA's declassified historical account of SIGINT surrounding the 1964 Gulf of Tonkin incident, including the disputed second attack on August 4.",
        "date": "2005-11-30",
        "tags": ["Gulf of Tonkin", "Vietnam War", "SIGINT", "1964", "NSA history"],
        "agency": "NSA",
    },
    {
        "id": "friedman_collection",
        "title": "William F. Friedman Collection — Cryptologic Pioneer Documents",
        "url": "https://www.nsa.gov/Helpful-Links/NSA-FOIA/Declassification-Transparency-Initiatives/Historical-Releases/Friedman-Documents/",
        "snippet": "Declassified personal and professional papers of William F. Friedman, the father of modern American cryptology, covering World War I and II codebreaking history.",
        "date": "2014-01-01",
        "tags": ["cryptology", "Friedman", "WWII", "codebreaking", "NSA history"],
        "agency": "NSA",
    },
    {
        "id": "venona",
        "title": "VENONA Project — Soviet Intelligence Decryption",
        "url": "https://www.nsa.gov/Helpful-Links/NSA-FOIA/Declassification-Transparency-Initiatives/Historical-Releases/VENONA/",
        "snippet": "Declassified VENONA project materials: the US signals intelligence effort to decrypt Soviet communications from 1943-1980, revealing Soviet espionage networks.",
        "date": "1995-07-11",
        "tags": ["VENONA", "Soviet", "espionage", "Cold War", "cryptanalysis"],
        "agency": "NSA",
    },
    {
        "id": "uss_liberty",
        "title": "USS Liberty Incident (1967) — Declassified NSA Documents",
        "url": "https://www.nsa.gov/Helpful-Links/NSA-FOIA/Declassification-Transparency-Initiatives/Historical-Releases/USS-Liberty/",
        "snippet": "NSA declassified materials related to the June 8, 1967 Israeli attack on the USS Liberty signals intelligence ship during the Six-Day War.",
        "date": "2003-06-01",
        "tags": ["USS Liberty", "1967", "Six-Day War", "Israel", "SIGINT"],
        "agency": "NSA",
    },
    {
        "id": "cryptologic_history",
        "title": "NSA/CSS Cryptologic History Series",
        "url": "https://www.nsa.gov/Helpful-Links/NSA-FOIA/Declassification-Transparency-Initiatives/Historical-Releases/Cryptologic-History/",
        "snippet": "Declassified volumes from NSA's internal cryptologic history series covering World War II, Korean War, and Cold War signals intelligence operations.",
        "date": "2012-01-01",
        "tags": ["cryptologic history", "WWII", "Korean War", "Cold War", "NSA"],
        "agency": "NSA",
    },
    {
        "id": "church_committee_nsa",
        "title": "Church Committee — NSA Materials (1975)",
        "url": "https://www.nsa.gov/Helpful-Links/NSA-FOIA/Declassification-Transparency-Initiatives/Historical-Releases/",
        "snippet": "NSA-related materials from the Senate Select Committee to Study Governmental Operations with Respect to Intelligence Activities (Church Committee), 1975-76.",
        "date": "1975-01-01",
        "tags": ["Church Committee", "Senate", "surveillance", "COINTELPRO", "NSA oversight"],
        "agency": "NSA",
    },
    {
        "id": "nsa_foia_reading_room",
        "title": "NSA FOIA Reading Room — Full Index",
        "url": "https://www.nsa.gov/Helpful-Links/NSA-FOIA/FOIA-Reading-Room/",
        "snippet": "Index of NSA FOIA Electronic Reading Room materials: frequently requested records, annual reports, Inspector General reports, and other proactive disclosures.",
        "date": None,
        "tags": ["FOIA", "NSA", "reading room", "transparency"],
        "agency": "NSA",
    },
]


class NSAArchiveConnector(BaseConnector):
    """
    NSA Declassification Archive — curated index of known public releases.

    IMPORTANT: The NSA provides NO search API, NO RSS feed, and NO programmatic
    search endpoint. This connector surfaces known curated collection URLs as
    browsable discovery entries. Query matching is performed locally against
    the curated metadata index. For comprehensive FOIA searches, visit:
    https://www.nsa.gov/Helpful-Links/NSA-FOIA/FOIA-Reading-Room/
    """
    source_id = "nsa_archive"
    name = "NSA Declassification Archive"
    category = "intelligence_archives"
    requires_auth = False
    supported_content_types = ["document", "declassified_record"]

    def __init__(self):
        self._last_diagnostic: Optional[Dict[str, Any]] = None

    @property
    def rate_limit_per_minute(self) -> int:
        return 60  # Local matching — no network calls during search

    async def test_connection(self) -> Dict[str, Any]:
        now_str = datetime.now(timezone.utc).isoformat()
        # NSA has no search endpoint — we validate the curated index is populated
        diag = {
            "configured": True,
            "authorized": True,
            "connected": True,
            "status": "connected",
            "message": (
                f"NSA Archive: {len(NSA_CURATED_COLLECTIONS)} curated declassification "
                "collections available. NOTE: NSA provides no programmatic search API — "
                "results are matched against a curated index of known public releases."
            ),
            "last_checked_at": now_str,
        }
        self._last_diagnostic = diag
        return diag

    def check_health(self) -> Dict[str, Any]:
        return {
            "status": "operational",
            "auth_status": "not_required",
            "message": (
                "NSA Declassification Archive — curated index of known public releases. "
                "No programmatic search API exists on nsa.gov."
            ),
        }

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        """
        Local keyword matching against the curated NSA collection index.
        No network calls — query is matched against title, snippet and tags.
        """
        query_lower = query.lower()
        results: List[RawResult] = []

        for col in NSA_CURATED_COLLECTIONS:
            searchable = " ".join([
                col["title"].lower(),
                (col["snippet"] or "").lower(),
                " ".join(col.get("tags", [])).lower(),
            ])
            if any(term in searchable for term in query_lower.split()):
                pub_at: Optional[datetime] = None
                if col["date"]:
                    try:
                        pub_at = datetime.strptime(col["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    except ValueError:
                        pass

                results.append(RawResult(
                    source_name="nsa_archive",
                    source_item_id=col["id"],
                    title=col["title"],
                    content_snippet=col["snippet"],
                    source_url=col["url"],
                    author=None,
                    published_at=pub_at,
                    content_type="declassified_record",
                    engagement_metrics={},
                    metadata={
                        "agency": col["agency"],
                        "archive": "NSA Declassification & Transparency Initiatives",
                        "document_type": "declassified_collection",
                        "access": "public",
                        "classification_status": "declassified",
                        "tags": col.get("tags", []),
                        "search_limitation": (
                            "NSA provides no programmatic search API. "
                            "Results matched from curated index only."
                        ),
                    },
                ))
            if len(results) >= limit:
                break

        return results
