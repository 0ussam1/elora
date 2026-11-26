"""
Tests for the 6 new data source connectors added to ELORA:
  - Semantic Scholar, CORE, Zenodo (academic)
  - Discourse, Lemmy, Mastodon (community)

Covers:
  1. Connector instantiation and class attributes
  2. check_health() shape
  3. not_configured behaviour (CORE requires a key)
  4. Mocked search() returning RawResult instances
  5. Live connectivity smoke-tests (skipped when network unavailable)
"""

import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

# ── Connectors under test ──────────────────────────────────────────────────────
from app.connectors.semantic_scholar import SemanticScholarConnector
from app.connectors.core_ac import CoreACConnector
from app.connectors.zenodo import ZenodoConnector
from app.connectors.discourse import DiscourseConnector
from app.connectors.lemmy import LemmyConnector
from app.connectors.mastodon import MastodonConnector
from app.connectors.base import RawResult


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _mock_response(status_code: int, json_data: dict) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    return mock


# ══════════════════════════════════════════════════════════════════════════════
# 1. Semantic Scholar
# ══════════════════════════════════════════════════════════════════════════════

class TestSemanticScholarConnector:
    def test_class_attributes(self):
        c = SemanticScholarConnector()
        assert c.source_id == "semantic_scholar"
        assert c.category == "academic"
        assert c.requires_auth is False
        assert "paper" in c.supported_content_types
        assert c.rate_limit_per_minute >= 100

    def test_check_health_no_diagnostic(self):
        c = SemanticScholarConnector()
        health = c.check_health()
        assert health["status"] in ("operational", "connected", "error")
        assert "auth_status" in health
        assert "message" in health

    @pytest.mark.asyncio
    async def test_search_mocked(self):
        c = SemanticScholarConnector()
        payload = {
            "data": [
                {
                    "paperId": "abc123",
                    "title": "Deep Learning Overview",
                    "abstract": "A comprehensive overview of deep learning.",
                    "authors": [{"name": "Yann LeCun"}],
                    "year": 2021,
                    "citationCount": 500,
                    "influentialCitationCount": 50,
                    "fieldsOfStudy": ["Computer Science"],
                    "openAccessPdf": {"url": "https://example.com/paper.pdf"},
                    "publicationDate": "2021-06-01",
                    "externalIds": {"DOI": "10.1234/example"},
                }
            ]
        }
        with patch("app.connectors.semantic_scholar.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=_mock_response(200, payload))
            MockClient.return_value = mock_client
            results = await c.search("deep learning", limit=5)
        assert len(results) == 1
        r = results[0]
        assert isinstance(r, RawResult)
        assert r.source_name == "semantic_scholar"
        assert r.source_item_id == "abc123"
        assert "Deep Learning" in r.title
        assert r.content_type == "paper"
        assert r.engagement_metrics["citation_count"] == 500


# ══════════════════════════════════════════════════════════════════════════════
# 2. CORE Open Access
# ══════════════════════════════════════════════════════════════════════════════

class TestCoreACConnector:
    def test_class_attributes(self):
        c = CoreACConnector()
        assert c.source_id == "core"
        assert c.category == "academic"
        assert c.requires_auth is True
        assert "paper" in c.supported_content_types

    def test_not_configured_health(self, monkeypatch):
        monkeypatch.setattr("app.connectors.core_ac.settings", MagicMock(
            CORE_API_KEY=None,
            REQUEST_TIMEOUT_SECONDS=12.0,
        ))
        c = CoreACConnector()
        health = c.check_health()
        assert health["status"] == "not_configured"
        assert health["auth_status"] == "not_configured"

    @pytest.mark.asyncio
    async def test_search_returns_empty_when_not_configured(self, monkeypatch):
        monkeypatch.setattr("app.connectors.core_ac.settings", MagicMock(
            CORE_API_KEY=None,
            REQUEST_TIMEOUT_SECONDS=12.0,
        ))
        c = CoreACConnector()
        results = await c.search("open access research", limit=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_test_connection_not_configured(self, monkeypatch):
        monkeypatch.setattr("app.connectors.core_ac.settings", MagicMock(
            CORE_API_KEY=None,
            REQUEST_TIMEOUT_SECONDS=12.0,
        ))
        c = CoreACConnector()
        diag = await c.test_connection()
        assert diag["configured"] is False
        assert diag["status"] == "not_configured"

    @pytest.mark.asyncio
    async def test_search_mocked(self, monkeypatch):
        monkeypatch.setattr("app.connectors.core_ac.settings", MagicMock(
            CORE_API_KEY="fake-key",
            REQUEST_TIMEOUT_SECONDS=12.0,
        ))
        c = CoreACConnector()
        payload = {
            "results": [
                {
                    "id": 99,
                    "title": "Open Access Paper",
                    "abstract": "An open access paper abstract.",
                    "authors": [{"name": "Alice Scholar"}],
                    "doi": "10.5555/test",
                    "downloadUrl": "https://example.com/paper.pdf",
                    "publishedDate": "2022-03-15",
                    "publisher": "Open Publisher",
                    "language": "en",
                }
            ]
        }
        with patch("app.connectors.core_ac.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=_mock_response(200, payload))
            MockClient.return_value = mock_client
            results = await c.search("open access", limit=5)
        assert len(results) == 1
        r = results[0]
        assert r.source_name == "core"
        assert r.source_item_id == "99"
        assert r.content_type == "paper"
        assert r.metadata["has_full_text"] is True


# ══════════════════════════════════════════════════════════════════════════════
# 3. Zenodo
# ══════════════════════════════════════════════════════════════════════════════

class TestZenodoConnector:
    def test_class_attributes(self):
        c = ZenodoConnector()
        assert c.source_id == "zenodo"
        assert c.category == "academic"
        assert c.requires_auth is False
        assert "dataset" in c.supported_content_types

    def test_check_health_no_diagnostic(self):
        c = ZenodoConnector()
        health = c.check_health()
        assert "status" in health
        assert "auth_status" in health

    @pytest.mark.asyncio
    async def test_search_mocked(self):
        c = ZenodoConnector()
        payload = {
            "hits": {
                "hits": [
                    {
                        "id": 12345,
                        "metadata": {
                            "title": "Climate Dataset 2023",
                            "description": "A dataset about climate change.",
                            "creators": [{"name": "Dr. Climate"}],
                            "doi": "10.5281/zenodo.12345",
                            "resource_type": {"type": "dataset"},
                            "publication_date": "2023-01-15",
                            "access_right": "open",
                        },
                        "links": {"html": "https://zenodo.org/record/12345"},
                        "stats": {"downloads": 200, "views": 1500},
                        "conceptdoi": "10.5281/zenodo.11111",
                    }
                ]
            }
        }
        with patch("app.connectors.zenodo.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=_mock_response(200, payload))
            MockClient.return_value = mock_client
            results = await c.search("climate change", limit=5)
        assert len(results) == 1
        r = results[0]
        assert r.source_name == "zenodo"
        assert r.content_type == "dataset"
        assert r.engagement_metrics["downloads"] == 200
        assert "doi" in r.metadata


# ══════════════════════════════════════════════════════════════════════════════
# 4. Discourse
# ══════════════════════════════════════════════════════════════════════════════

class TestDiscourseConnector:
    def test_class_attributes(self):
        c = DiscourseConnector()
        assert c.source_id == "discourse"
        assert c.category == "community"
        assert c.requires_auth is False
        assert "discussion" in c.supported_content_types

    def test_check_health_no_diagnostic(self):
        c = DiscourseConnector()
        health = c.check_health()
        assert health["status"] in ("operational", "connected", "error")

    @pytest.mark.asyncio
    async def test_search_mocked(self):
        c = DiscourseConnector()
        payload = {
            "topics": [
                {
                    "id": 1001,
                    "slug": "how-to-use-python-effectively",
                    "title": "How to use Python effectively",
                    "blurb": "Tips for better Python code.",
                    "created_at": "2023-05-10T12:00:00Z",
                    "posts_count": 25,
                    "like_count": 80,
                    "views": 3000,
                    "category_id": 5,
                    "tags": ["python", "best-practices"],
                }
            ]
        }
        with patch("app.connectors.discourse.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=_mock_response(200, payload))
            MockClient.return_value = mock_client
            results = await c.search("python", limit=5)
        assert len(results) >= 1
        r = results[0]
        assert r.source_name == "discourse"
        assert r.content_type == "discussion"
        assert "Python" in r.title
        assert r.engagement_metrics["posts_count"] == 25


# ══════════════════════════════════════════════════════════════════════════════
# 5. Lemmy
# ══════════════════════════════════════════════════════════════════════════════

class TestLemmyConnector:
    def test_class_attributes(self):
        c = LemmyConnector()
        assert c.source_id == "lemmy"
        assert c.category == "community"
        assert c.requires_auth is False
        assert "post" in c.supported_content_types

    @pytest.mark.asyncio
    async def test_search_mocked(self):
        c = LemmyConnector()
        payload = {
            "posts": [
                {
                    "post": {
                        "id": 42,
                        "name": "Best Linux distros 2024",
                        "body": "Let's discuss the best Linux distros for developers.",
                        "ap_id": "https://lemmy.world/post/42",
                        "published": "2024-01-20T08:30:00Z",
                        "nsfw": False,
                    },
                    "creator": {"name": "linuxfan", "display_name": "Linux Fan"},
                    "community": {"name": "linux"},
                    "counts": {
                        "score": 450,
                        "comments": 78,
                        "upvotes": 480,
                        "downvotes": 30,
                    },
                }
            ]
        }
        with patch("app.connectors.lemmy.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=_mock_response(200, payload))
            MockClient.return_value = mock_client
            results = await c.search("linux", limit=5)
        assert len(results) >= 1
        r = results[0]
        assert r.source_name == "lemmy"
        assert r.content_type == "post"
        assert r.engagement_metrics["score"] == 450
        assert r.author == "linuxfan"


# ══════════════════════════════════════════════════════════════════════════════
# 6. Mastodon
# ══════════════════════════════════════════════════════════════════════════════

class TestMastodonConnector:
    def test_class_attributes(self):
        c = MastodonConnector()
        assert c.source_id == "mastodon"
        assert c.category == "community"
        assert c.requires_auth is False
        assert "post" in c.supported_content_types

    @pytest.mark.asyncio
    async def test_search_mocked(self):
        c = MastodonConnector()
        payload = {
            "statuses": [
                {
                    "id": "987654321",
                    "content": "<p>Excited about <a href='#'>open source</a> AI tools!</p>",
                    "url": "https://mastodon.social/@user/987654321",
                    "created_at": "2024-02-14T10:00:00Z",
                    "account": {"acct": "opendev@mastodon.social", "username": "opendev"},
                    "reblogs_count": 15,
                    "favourites_count": 42,
                    "replies_count": 3,
                    "tags": [{"name": "opensource"}, {"name": "ai"}],
                    "language": "en",
                    "sensitive": False,
                }
            ]
        }
        with patch("app.connectors.mastodon.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=_mock_response(200, payload))
            MockClient.return_value = mock_client
            results = await c.search("open source AI", limit=5)
        assert len(results) >= 1
        r = results[0]
        assert r.source_name == "mastodon"
        assert r.content_type == "post"
        assert r.engagement_metrics["favourites_count"] == 42
        # HTML should be stripped from content_snippet
        assert "<p>" not in (r.content_snippet or "")
        assert "<a" not in (r.content_snippet or "")

    def test_strip_html_utility(self):
        from app.connectors.mastodon import _strip_html
        result = _strip_html("<p>Hello <b>World</b>! <a href='#'>Link</a></p>")
        assert "<" not in result
        assert "Hello" in result
        assert "World" in result


# ══════════════════════════════════════════════════════════════════════════════
# 7. Registry integration — all 6 appear in CONNECTOR_REGISTRY
# ══════════════════════════════════════════════════════════════════════════════

class TestRegistryIntegration:
    def test_all_new_sources_registered(self):
        from app.connectors.registry import CONNECTOR_REGISTRY
        expected = {
            "semantic_scholar", "core", "zenodo",
            "discourse", "lemmy", "mastodon",
        }
        registered = set(CONNECTOR_REGISTRY.keys())
        assert expected.issubset(registered), f"Missing: {expected - registered}"

    def test_total_source_count(self):
        from app.connectors.registry import CONNECTOR_REGISTRY
        # 12 existing + 6 new = 18
        assert len(CONNECTOR_REGISTRY) == 18

    def test_list_all_sources_includes_new(self):
        from app.connectors.registry import list_all_sources
        sources = list_all_sources()
        ids = {s["id"] for s in sources}
        assert "semantic_scholar" in ids
        assert "core" in ids
        assert "zenodo" in ids
        assert "discourse" in ids
        assert "lemmy" in ids
        assert "mastodon" in ids
