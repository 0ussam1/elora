"""
ICIJ Offshore Leaks Database Connector
=======================================
Source: https://offshoreleaks.icij.org/
API: Official W3C Reconciliation API — https://offshoreleaks.icij.org/api/v1/reconcile
     Node detail: https://offshoreleaks.icij.org/nodes/{id}.json
Access: Completely public — no authentication or API key required.
Content: Entities, officers, intermediaries and addresses from:
         - Panama Papers (2016)
         - Pandora Papers (2021)
         - Paradise Papers (2017)
         - Offshore Leaks (2013)
         - Bahamas Leaks (2016)
         - Luxembourg Leaks (2014)
Scope: Corporate entities, registered agents, beneficial owners, offshore addresses.
       NOT private individuals' complete financial records.
       The ICIJ publishes only entity-level metadata — not raw private documents.
Legal: ICIJ releases data in the public interest under journalism/investigative reporting
       norms. Data is verified by ICIJ member journalists.
"""
import httpx
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.connectors.base import BaseConnector, RawResult
from app.core.config import settings

logger = logging.getLogger(__name__)

RECONCILE_URL = "https://offshoreleaks.icij.org/api/v1/reconcile"
NODE_URL = "https://offshoreleaks.icij.org/nodes/{node_id}.json"
NODE_PAGE = "https://offshoreleaks.icij.org/nodes/{node_id}"

# Map ICIJ entity types to human-readable labels
_TYPE_LABELS = {
    "Entity": "Offshore Entity",
    "Officer": "Officer / Beneficial Owner",
    "Intermediary": "Registered Agent / Intermediary",
    "Address": "Registered Address",
}

# Leak source → year
_SOURCE_YEARS: Dict[str, int] = {
    "panama_papers": 2016,
    "pandora_papers": 2021,
    "paradise_papers": 2017,
    "offshore_leaks": 2013,
    "bahamas_leaks": 2016,
    "luxembourg_leaks": 2014,
}


class ICIJOffshoreLeaksConnector(BaseConnector):
    """
    ICIJ Offshore Leaks Database — official public Reconciliation API.
    Searches for offshore entities, officers, intermediaries and addresses
    across all major ICIJ financial investigation leak datasets.

    Uses the W3C Reconciliation Service API (no auth required).
    Entity metadata is retrieved via the public Node JSON API.
    """
    source_id = "icij_offshore"
    name = "ICIJ Offshore Leaks Database"
    category = "intelligence_archives"
    requires_auth = False
    supported_content_types = ["investigative_record", "financial_entity"]

    HEADERS = {
        "User-Agent": "ELORA-Research-Engine/1.0 (academic/open-source; contact: researcher@example.com)",
        "Accept": "application/json",
    }

    def __init__(self):
        self._last_diagnostic: Optional[Dict[str, Any]] = None

    @property
    def rate_limit_per_minute(self) -> int:
        return 30

    async def test_connection(self) -> Dict[str, Any]:
        now_str = datetime.now(timezone.utc).isoformat()
        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    RECONCILE_URL,
                    data={"queries": '{"q0": {"query": "test"}}'},
                    headers=self.HEADERS,
                )
            if resp.status_code in (200, 201):
                diag = {
                    "configured": True, "authorized": True, "connected": True,
                    "status": "connected",
                    "message": "ICIJ Offshore Leaks Reconciliation API is reachable (public, no auth)",
                    "last_checked_at": now_str,
                }
            else:
                diag = {
                    "configured": True, "authorized": False, "connected": False,
                    "status": "error",
                    "message": f"ICIJ Reconciliation API returned HTTP {resp.status_code}",
                    "last_checked_at": now_str,
                }
        except Exception as e:
            diag = {
                "configured": True, "authorized": False, "connected": False,
                "status": "error",
                "message": f"Network error reaching ICIJ Offshore Leaks API: {e}",
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
            "message": (
                "ICIJ Offshore Leaks — public Reconciliation API covering Panama Papers, "
                "Pandora Papers, Paradise Papers, and more."
            ),
        }

    async def _fetch_node_detail(self, client: httpx.AsyncClient, node_id: str) -> Optional[Dict[str, Any]]:
        """Fetch additional metadata for a node from the JSON detail endpoint."""
        try:
            resp = await client.get(
                NODE_URL.format(node_id=node_id),
                headers=self.HEADERS,
                timeout=6.0,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        """
        Search using the ICIJ W3C Reconciliation API.
        Builds a batch of query keys and resolves top candidates.
        """
        results: List[RawResult] = []

        # Build batch reconciliation query
        import json
        queries_dict = {f"q{i}": {"query": query, "limit": min(limit, 10)} for i in range(1)}
        queries_json = json.dumps(queries_dict)

        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    RECONCILE_URL,
                    data={"queries": queries_json},
                    headers=self.HEADERS,
                )
                if resp.status_code not in (200, 201):
                    logger.warning(f"ICIJ Reconciliation API returned {resp.status_code}")
                    return []

                data = resp.json()
                candidates = []
                for key in data:
                    candidates.extend(data[key].get("result", []))

                # Sort by score descending
                candidates.sort(key=lambda c: c.get("score", 0), reverse=True)

                for candidate in candidates[:limit]:
                    node_id = str(candidate.get("id", ""))
                    name = candidate.get("name", "Unknown Entity")
                    score = candidate.get("score", 0)
                    matched = candidate.get("match", False)
                    types = candidate.get("types") or candidate.get("type") or []
                    if types and isinstance(types, list) and isinstance(types[0], dict):
                        entity_type_raw = types[0].get("name") or types[0].get("id", "Entity")
                        if "/" in entity_type_raw:
                            entity_type_raw = entity_type_raw.rstrip("/").split("/")[-1].title()
                    else:
                        entity_type_raw = "Entity"
                    entity_label = _TYPE_LABELS.get(entity_type_raw, entity_type_raw)
                    description = candidate.get("description", "")
                    url = NODE_PAGE.format(node_id=node_id)

                    # Parse source/leak from description
                    source_id_raw = ""
                    if description:
                        for src_key in _SOURCE_YEARS:
                            if src_key.replace("_", " ").lower() in description.lower() or src_key in description.lower():
                                source_id_raw = src_key
                                break

                    # Try to get additional details from node JSON endpoint
                    node_detail = await self._fetch_node_detail(client, node_id)
                    jurisdiction = None
                    pub_at: Optional[datetime] = None
                    if isinstance(node_detail, list) and node_detail:
                        first_node = node_detail[0] if isinstance(node_detail[0], dict) else {}
                        props = first_node.get("data", {}).get("properties", {})
                        jurisdiction = props.get("jurisdiction_description") or props.get("countries") or props.get("jurisdiction")
                        if not source_id_raw and props.get("sourceID"):
                            source_id_raw = props["sourceID"].lower().replace(" ", "_")
                        inc_date = props.get("incorporation_date") or props.get("start_date")
                        if inc_date:
                            try:
                                pub_at = datetime.fromisoformat(str(inc_date).replace("Z", "+00:00"))
                            except (ValueError, TypeError):
                                pass
                    elif isinstance(node_detail, dict):
                        node_data = node_detail.get("node", {})
                        jurisdiction = node_data.get("jurisdiction") or node_data.get("countries")
                        inc_date = node_data.get("incorporation_date") or node_data.get("start_date")
                        if inc_date:
                            try:
                                pub_at = datetime.fromisoformat(str(inc_date).replace("Z", "+00:00"))
                            except (ValueError, TypeError):
                                pass

                    # Determine publication year from known leak date
                    if not pub_at and source_id_raw in _SOURCE_YEARS:
                        pub_at = datetime(_SOURCE_YEARS[source_id_raw], 1, 1, tzinfo=timezone.utc)

                    leak_name = source_id_raw.replace("_", " ").title() if source_id_raw else "Unknown Leak"

                    snippet = (
                        f"{entity_label} in the {leak_name}. "
                        f"Confidence score: {score:.1f}. "
                        + (f"Jurisdiction: {jurisdiction}. " if jurisdiction else "")
                        + (description[:200] if description else "")
                    ).strip()

                    results.append(RawResult(
                        source_name="icij_offshore",
                        source_item_id=node_id,
                        title=f"{name} ({entity_label})",
                        content_snippet=snippet[:500] if snippet else None,
                        source_url=url,
                        author=None,
                        published_at=pub_at,
                        content_type="investigative_record",
                        engagement_metrics={"reconciliation_score": score, "exact_match": matched},
                        metadata={
                            "agency": "ICIJ",
                            "archive": "ICIJ Offshore Leaks Database",
                            "document_type": "investigative_leaked_public",
                            "entity_type": entity_type_raw,
                            "entity_label": entity_label,
                            "leak_source": leak_name,
                            "jurisdiction": jurisdiction,
                            "classification_status": "leaked_public_interest",
                            "node_id": node_id,
                            "access": "public",
                            "note": (
                                "ICIJ publishes entity-level metadata only. "
                                "Raw source documents are not public. "
                                "Data verified by ICIJ investigative journalists."
                            ),
                        },
                    ))

        except Exception as e:
            logger.error(f"ICIJ Offshore Leaks search failed: {e}")

        return results
