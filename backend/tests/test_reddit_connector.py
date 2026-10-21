import pytest
from unittest.mock import patch, MagicMock
from app.connectors.reddit import RedditConnector
from app.core.config import settings

@pytest.mark.asyncio
async def test_reddit_not_configured():
    conn = RedditConnector()
    with patch.object(settings, "REDDIT_CLIENT_ID", None), patch.object(settings, "REDDIT_CLIENT_SECRET", None):
        health = conn.check_health()
        assert health["status"] == "not_configured"
        assert health["auth_status"] == "not_configured"

        diag = await conn.test_connection()
        assert diag["configured"] is False
        assert diag["authorized"] is False
        assert diag["connected"] is False
        assert diag["status"] == "not_configured"

        results = await conn.search("python")
        assert results == []

@pytest.mark.asyncio
async def test_reddit_configured_untested():
    conn = RedditConnector()
    with patch.object(settings, "REDDIT_CLIENT_ID", "test_id"), patch.object(settings, "REDDIT_CLIENT_SECRET", "test_secret"):
        health = conn.check_health()
        assert health["status"] == "configured"
        assert health["auth_status"] == "configured"

@pytest.mark.asyncio
async def test_reddit_invalid_credentials_401():
    conn = RedditConnector()
    with patch.object(settings, "REDDIT_CLIENT_ID", "bad_id"), patch.object(settings, "REDDIT_CLIENT_SECRET", "bad_secret"):
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            diag = await conn.test_connection()
            assert diag["configured"] is True
            assert diag["authorized"] is False
            assert diag["connected"] is False
            assert diag["status"] == "pending_authorization"
            assert "Invalid credentials" in diag["message"]

@pytest.mark.asyncio
async def test_reddit_access_forbidden_403():
    conn = RedditConnector()
    with patch.object(settings, "REDDIT_CLIENT_ID", "pending_app_id"), patch.object(settings, "REDDIT_CLIENT_SECRET", "secret"):
        mock_response = MagicMock()
        mock_response.status_code = 403

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            diag = await conn.test_connection()
            assert diag["configured"] is True
            assert diag["authorized"] is False
            assert diag["connected"] is False
            assert diag["status"] == "pending_authorization"
            assert "Access denied" in diag["message"]

@pytest.mark.asyncio
async def test_reddit_rate_limited_429():
    conn = RedditConnector()
    with patch.object(settings, "REDDIT_CLIENT_ID", "id"), patch.object(settings, "REDDIT_CLIENT_SECRET", "secret"):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"retry-after": "45"}

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            diag = await conn.test_connection()
            assert diag["configured"] is True
            assert diag["connected"] is False
            assert diag["status"] == "rate_limited"

@pytest.mark.asyncio
async def test_reddit_successful_connection_and_search():
    conn = RedditConnector()
    with patch.object(settings, "REDDIT_CLIENT_ID", "valid_id"), patch.object(settings, "REDDIT_CLIENT_SECRET", "valid_secret"):
        # Mock token response
        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {
            "access_token": "mock_token_xyz",
            "token_type": "bearer",
            "expires_in": 3600
        }

        # Mock probe response
        mock_probe_resp = MagicMock()
        mock_probe_resp.status_code = 200
        mock_probe_resp.headers = {"x-ratelimit-remaining": "99", "x-ratelimit-reset": "60"}

        # Mock search response
        mock_search_resp = MagicMock()
        mock_search_resp.status_code = 200
        mock_search_resp.json.return_value = {
            "data": {
                "children": [
                    {
                        "data": {
                            "id": "abc123",
                            "title": "Discussion on Python ML libraries bug",
                            "selftext": "Users encounter unexpected memory issue in data cleaning pipeline.",
                            "permalink": "/r/Python/comments/abc123/discussion_on_python/",
                            "author": "dev_user",
                            "created_utc": 1700000000,
                            "score": 42,
                            "num_comments": 15,
                            "subreddit": "Python"
                        }
                    }
                ]
            }
        }

        with patch("httpx.AsyncClient.post", return_value=mock_token_resp):
            with patch("httpx.AsyncClient.get", side_effect=[mock_probe_resp, mock_search_resp]):
                diag = await conn.test_connection()
                assert diag["configured"] is True
                assert diag["authorized"] is True
                assert diag["connected"] is True
                assert diag["status"] == "connected"

                # Execute search
                results = await conn.search("Python ML libraries")
                assert len(results) == 1
                assert results[0].source_name == "reddit"
                assert results[0].title == "Discussion on Python ML libraries bug"
                assert results[0].source_url == "https://www.reddit.com/r/Python/comments/abc123/discussion_on_python/"
                assert results[0].engagement_metrics["score"] == 42
                assert results[0].engagement_metrics["num_comments"] == 15
