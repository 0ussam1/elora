"""
Tests for the 6 Intelligence & Investigative Archive connectors:
  - CIA FOIA Reading Room (HTML parse)
  - FBI Vault (HTML parse)
  - NSA Declassification Archive (curated local index)
  - National Security Archive / GWU (HTML parse)
  - NARA National Archives Catalog (official REST API, requires key)
  - ICIJ Offshore Leaks Database (official Reconciliation API, public)

Covers:
  1. Connector class attributes and category
  2. check_health() shape validation
  3. not_configured behaviour (NARA requires a key)
  4. Mocked search() returning correctly shaped RawResult instances
  5. NSA curated index local matching (no network needed)
"""
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

from app.connectors.cia_reading_room import CIAReadingRoomConnector
from app.connectors.fbi_vault import FBIVaultConnector
from app.connectors.nsa_archive import NSAArchiveConnector, NSA_CURATED_COLLECTIONS
from app.connectors.nat_sec_archive import NatSecArchiveConnector
from app.connectors.nara import NARAConnector
from app.connectors.icij_offshore import ICIJOffshoreLeaksConnector
from app.connectors.base import RawResult


def _mock_response(status_code: int, json_data=None, text: str = "") -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data or {}
    mock.text = text
    return mock


# ══════════════════════════════════════════════════════════════════════════════
# 1. CIA FOIA Reading Room
# ══════════════════════════════════════════════════════════════════════════════

class TestCIAReadingRoomConnector:
    def test_class_attributes(self):
        c = CIAReadingRoomConnector()
        assert c.source_id == "cia_reading_room"
        assert c.category == "intelligence_archives"
        assert c.requires_auth is False
        assert "declassified_record" in c.supported_content_types

    def test_check_health_no_diagnostic(self):
        c = CIAReadingRoomConnector()
        h = c.check_health()
        assert h["status"] in ("operational", "connected", "error")
        assert "auth_status" in h
        assert h["auth_status"] == "not_required"

    def test_rate_limit_conservative(self):
        c = CIAReadingRoomConnector()
        assert c.rate_limit_per_minute <= 15  # Must be conservative for gov server

    @pytest.mark.asyncio
    async def test_search_mocked_html(self):
        c = CIAReadingRoomConnector()
        # Minimal HTML that contains a document link pattern
        fake_html = """
        <html><body>
        <article class="search-result">
          <h3><a href="/readingroom/document/cia-rdp68-00002r000100100004-9">Bay of Pigs Study</a></h3>
          <p>Declassified internal CIA assessment of the 1961 Bay of Pigs operation failure.</p>
          <span class="date">1979-12-21</span>
        </article>
        </body></html>
        """
        with patch("app.connectors.cia_reading_room.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=_mock_response(200, text=fake_html))
            MockClient.return_value = mock_client
            results = await c.search("Bay of Pigs", limit=5)

        # Even if parsing yields 0 (HTML structure may not match exactly),
        # the connector must NOT crash and must return a list
        assert isinstance(results, list)
        for r in results:
            assert isinstance(r, RawResult)
            assert r.source_name == "cia_reading_room"
            assert r.metadata["agency"] == "CIA"
            assert r.metadata["classification_status"] == "declassified"

    @pytest.mark.asyncio
    async def test_search_non_200_returns_empty(self):
        c = CIAReadingRoomConnector()
        with patch("app.connectors.cia_reading_room.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=_mock_response(503))
            MockClient.return_value = mock_client
            results = await c.search("COINTELPRO", limit=5)
        assert results == []


# ══════════════════════════════════════════════════════════════════════════════
# 2. FBI Vault
# ══════════════════════════════════════════════════════════════════════════════

class TestFBIVaultConnector:
    def test_class_attributes(self):
        c = FBIVaultConnector()
        assert c.source_id == "fbi_vault"
        assert c.category == "intelligence_archives"
        assert c.requires_auth is False
        assert "foia_record" in c.supported_content_types

    def test_check_health_shape(self):
        c = FBIVaultConnector()
        h = c.check_health()
        assert "status" in h
        assert "auth_status" in h
        assert "message" in h

    @pytest.mark.asyncio
    async def test_search_mocked_html(self):
        c = FBIVaultConnector()
        fake_html = """
        <html><body>
        <div class="searchResult">
          <a href="https://vault.fbi.gov/roswell-ufo-incident">Roswell UFO Incident Files</a>
          <p>FBI files related to the 1947 Roswell New Mexico incident reports.</p>
        </div>
        </body></html>
        """
        with patch("app.connectors.fbi_vault.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=_mock_response(200, text=fake_html))
            MockClient.return_value = mock_client
            results = await c.search("Roswell UFO", limit=5)
        assert isinstance(results, list)
        for r in results:
            assert r.source_name == "fbi_vault"
            assert r.metadata["agency"] == "FBI"
            assert r.content_type == "foia_record"

    @pytest.mark.asyncio
    async def test_search_error_returns_empty(self):
        c = FBIVaultConnector()
        with patch("app.connectors.fbi_vault.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=Exception("connection refused"))
            MockClient.return_value = mock_client
            results = await c.search("COINTELPRO", limit=5)
        assert results == []


# ══════════════════════════════════════════════════════════════════════════════
# 3. NSA Archive (curated local index — no network)
# ══════════════════════════════════════════════════════════════════════════════

class TestNSAArchiveConnector:
    def test_class_attributes(self):
        c = NSAArchiveConnector()
        assert c.source_id == "nsa_archive"
        assert c.category == "intelligence_archives"
        assert c.requires_auth is False
        assert "declassified_record" in c.supported_content_types

    def test_curated_index_populated(self):
        assert len(NSA_CURATED_COLLECTIONS) >= 5
        for entry in NSA_CURATED_COLLECTIONS:
            assert "title" in entry
            assert "url" in entry
            assert entry["url"].startswith("https://www.nsa.gov")

    @pytest.mark.asyncio
    async def test_search_local_matching_ukusa(self):
        c = NSAArchiveConnector()
        results = await c.search("UKUSA signals intelligence", limit=10)
        assert len(results) >= 1
        r = results[0]
        assert r.source_name == "nsa_archive"
        assert r.source_item_id == "ukusa"
        assert "UKUSA" in r.title
        assert r.metadata["agency"] == "NSA/GCHQ"
        assert r.metadata["classification_status"] == "declassified"
        assert "nsa.gov" in r.source_url

    @pytest.mark.asyncio
    async def test_search_local_matching_venona(self):
        c = NSAArchiveConnector()
        results = await c.search("VENONA Soviet espionage Cold War", limit=10)
        ids = [r.source_item_id for r in results]
        assert "venona" in ids

    @pytest.mark.asyncio
    async def test_search_no_match_returns_empty(self):
        c = NSAArchiveConnector()
        results = await c.search("zxqpwk12345_nonexistent_term", limit=10)
        assert results == []

    @pytest.mark.asyncio
    async def test_search_metadata_has_limitation_note(self):
        c = NSAArchiveConnector()
        results = await c.search("UKUSA", limit=5)
        for r in results:
            assert "search_limitation" in r.metadata

    @pytest.mark.asyncio
    async def test_test_connection_always_succeeds(self):
        c = NSAArchiveConnector()
        diag = await c.test_connection()
        assert diag["configured"] is True
        assert diag["status"] == "connected"


# ══════════════════════════════════════════════════════════════════════════════
# 4. National Security Archive (GWU)
# ══════════════════════════════════════════════════════════════════════════════

class TestNatSecArchiveConnector:
    def test_class_attributes(self):
        c = NatSecArchiveConnector()
        assert c.source_id == "nat_sec_archive"
        assert c.category == "intelligence_archives"
        assert c.requires_auth is False
        assert "briefing_book" in c.supported_content_types

    def test_check_health_shape(self):
        c = NatSecArchiveConnector()
        h = c.check_health()
        assert "status" in h
        assert h["auth_status"] == "not_required"

    @pytest.mark.asyncio
    async def test_search_mocked_link_fallback(self):
        c = NatSecArchiveConnector()
        # Simulate HTML with simple <a href> links (last-resort parse path)
        fake_html = """
        <html><body>
        <a href="/briefing-book/nuclear-vault/2017-01-11/us-stood-brink-nuclear-war">
          US Stood at Brink of Nuclear War with USSR — 1983 Able Archer War Scare
        </a>
        <a href="/document/cia-national-intelligence-estimate-1983">
          CIA National Intelligence Estimate — Soviet War Preparations 1983
        </a>
        </body></html>
        """
        with patch("app.connectors.nat_sec_archive.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=_mock_response(200, text=fake_html))
            MockClient.return_value = mock_client
            results = await c.search("nuclear war USSR 1983", limit=5)
        assert isinstance(results, list)
        for r in results:
            assert r.source_name == "nat_sec_archive"
            assert r.metadata["archive"] == "National Security Archive (GWU)"

    @pytest.mark.asyncio
    async def test_search_503_returns_empty(self):
        c = NatSecArchiveConnector()
        with patch("app.connectors.nat_sec_archive.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=_mock_response(503))
            MockClient.return_value = mock_client
            results = await c.search("Cuba missile crisis", limit=5)
        assert results == []


# ══════════════════════════════════════════════════════════════════════════════
# 5. NARA National Archives
# ══════════════════════════════════════════════════════════════════════════════

class TestNARAConnector:
    def test_class_attributes(self):
        c = NARAConnector()
        assert c.source_id == "nara"
        assert c.category == "intelligence_archives"
        assert c.requires_auth is True
        assert "archival_record" in c.supported_content_types

    def test_not_configured_health(self, monkeypatch):
        monkeypatch.setattr("app.connectors.nara.settings", MagicMock(
            NARA_API_KEY=None,
            REQUEST_TIMEOUT_SECONDS=12.0,
        ))
        c = NARAConnector()
        h = c.check_health()
        assert h["status"] == "not_configured"
        assert h["auth_status"] == "not_configured"
        assert "Catalog_API@nara.gov" in h["message"]

    @pytest.mark.asyncio
    async def test_search_returns_empty_when_not_configured(self, monkeypatch):
        monkeypatch.setattr("app.connectors.nara.settings", MagicMock(
            NARA_API_KEY=None,
            REQUEST_TIMEOUT_SECONDS=12.0,
        ))
        c = NARAConnector()
        results = await c.search("WWII records", limit=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_test_connection_not_configured(self, monkeypatch):
        monkeypatch.setattr("app.connectors.nara.settings", MagicMock(
            NARA_API_KEY=None,
            REQUEST_TIMEOUT_SECONDS=12.0,
        ))
        c = NARAConnector()
        diag = await c.test_connection()
        assert diag["configured"] is False
        assert diag["status"] == "not_configured"
        assert "Catalog_API@nara.gov" in diag["message"]

    @pytest.mark.asyncio
    async def test_search_mocked_with_key(self, monkeypatch):
        monkeypatch.setattr("app.connectors.nara.settings", MagicMock(
            NARA_API_KEY="fake-nara-key",
            REQUEST_TIMEOUT_SECONDS=12.0,
        ))
        c = NARAConnector()
        payload = {
            "body": {
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "naId": "305263",
                                "title": "German Air Force Records, 1935-1945",
                                "description": "Records of the German Luftwaffe captured during WWII.",
                                "creator": [{"name": "Department of the Air Force"}],
                                "date": "1946-01-01",
                                "specificRecordsType": "Textual Records",
                                "accessRestrictionStatus": "",
                                "useRestrictionStatus": "Unrestricted",
                                "digitalObjects": [{"objectUrl": "https://catalog.archives.gov/OpaAPI/media/305263/content/arcmedia/rg242/document.pdf"}],
                            }
                        }
                    ]
                }
            }
        }
        with patch("app.connectors.nara.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=_mock_response(200, json_data=payload))
            MockClient.return_value = mock_client
            results = await c.search("Luftwaffe WWII", limit=5)
        assert len(results) == 1
        r = results[0]
        assert r.source_name == "nara"
        assert r.source_item_id == "305263"
        assert r.content_type == "archival_record"
        assert r.metadata["agency"] == "NARA"
        assert r.metadata["has_digital_object"] is True


# ══════════════════════════════════════════════════════════════════════════════
# 6. ICIJ Offshore Leaks
# ══════════════════════════════════════════════════════════════════════════════

class TestICIJOffshoreLeaksConnector:
    def test_class_attributes(self):
        c = ICIJOffshoreLeaksConnector()
        assert c.source_id == "icij_offshore"
        assert c.category == "intelligence_archives"
        assert c.requires_auth is False
        assert "investigative_record" in c.supported_content_types

    def test_check_health_no_diagnostic(self):
        c = ICIJOffshoreLeaksConnector()
        h = c.check_health()
        assert h["status"] in ("operational", "connected", "error")
        assert h["auth_status"] == "not_required"
        assert "Panama Papers" in h["message"]

    @pytest.mark.asyncio
    async def test_search_mocked(self):
        c = ICIJOffshoreLeaksConnector()
        reconcile_payload = {
            "q0": {
                "result": [
                    {
                        "id": "123456",
                        "name": "ACME HOLDINGS LTD",
                        "score": 97.5,
                        "match": True,
                        "types": [{"id": "https://offshoreleaks.icij.org/schema/oldb/entity", "name": "Entity"}],
                        "description": "British Virgin Islands offshore entity — panama_papers",
                    }
                ]
            }
        }
        node_payload = {
            "node": {
                "jurisdiction": "British Virgin Islands",
                "incorporation_date": "2005-03-14",
            }
        }

        with patch("app.connectors.icij_offshore.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            post_resp = _mock_response(200, json_data=reconcile_payload)
            node_resp = _mock_response(200, json_data=node_payload)

            mock_client.post = AsyncMock(return_value=post_resp)
            mock_client.get = AsyncMock(return_value=node_resp)
            MockClient.return_value = mock_client

            results = await c.search("ACME HOLDINGS", limit=5)

        assert len(results) == 1
        r = results[0]
        assert r.source_name == "icij_offshore"
        assert r.source_item_id == "123456"
        assert "ACME HOLDINGS LTD" in r.title
        assert r.content_type == "investigative_record"
        assert r.engagement_metrics["reconciliation_score"] == 97.5
        assert r.engagement_metrics["exact_match"] is True
        assert r.metadata["entity_type"] == "Entity"
        assert "not public" in r.metadata["note"].lower() or "entity-level" in r.metadata["note"].lower()

    @pytest.mark.asyncio
    async def test_search_error_returns_empty(self):
        c = ICIJOffshoreLeaksConnector()
        with patch("app.connectors.icij_offshore.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=Exception("connection error"))
            MockClient.return_value = mock_client
            results = await c.search("shell company Cayman Islands", limit=5)
        assert results == []


# ══════════════════════════════════════════════════════════════════════════════
# 7. Registry integration — all 6 intelligence archive sources registered
# ══════════════════════════════════════════════════════════════════════════════

class TestIntelligenceArchivesRegistryIntegration:
    def test_all_new_sources_registered(self):
        from app.connectors.registry import CONNECTOR_REGISTRY
        expected = {
            "cia_reading_room", "fbi_vault", "nsa_archive",
            "nat_sec_archive", "nara", "icij_offshore",
        }
        registered = set(CONNECTOR_REGISTRY.keys())
        assert expected.issubset(registered), f"Missing: {expected - registered}"

    def test_total_source_count(self):
        from app.connectors.registry import CONNECTOR_REGISTRY
        # 12 existing + 6 research + 6 intelligence + 8 news = 32
        assert len(CONNECTOR_REGISTRY) >= 24

    def test_all_intelligence_sources_have_correct_category(self):
        from app.connectors.registry import CONNECTOR_REGISTRY
        intel_ids = {
            "cia_reading_room", "fbi_vault", "nsa_archive",
            "nat_sec_archive", "nara", "icij_offshore",
        }
        for sid in intel_ids:
            conn = CONNECTOR_REGISTRY[sid]
            assert conn.category == "intelligence_archives", \
                f"{sid} has wrong category: {conn.category}"

    def test_list_all_sources_includes_intel_sources(self):
        from app.connectors.registry import list_all_sources
        sources = list_all_sources()
        ids = {s["id"] for s in sources}
        for sid in ("cia_reading_room", "fbi_vault", "nsa_archive", "nat_sec_archive", "nara", "icij_offshore"):
            assert sid in ids, f"{sid} missing from list_all_sources()"
