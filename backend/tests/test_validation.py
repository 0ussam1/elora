"""
Tests for Multi-Layer Search Result Validation, False-Validation Prevention,
Source-Specific Verification, Provenance, and Validation Cache.

Covers all 12 required scenarios:
  1. Valid accessible article
  2. Valid discussion
  3. Deleted post
  4. Genuine 404 URL
  5. 410 URL
  6. Redirect
  7. Soft 404
  8. CAPTCHA response
  9. HTTP 200 with empty content
 10. Valid API record with inaccessible external URL
 11. Temporarily unavailable server
 12. Content mismatch with original source
"""
import pytest
import httpx
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.models.database import ResearchResult, ValidationCache
from app.pipeline.validator import (
    ResultValidator,
    STATUS_VERIFIED,
    STATUS_PARTIALLY_VERIFIED,
    STATUS_INACCESSIBLE,
    STATUS_DELETED,
    STATUS_NOT_FOUND,
    STATUS_MISMATCH,
    _url_hash,
)


def _make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _make_result(
    source_name="web_search",
    source_item_id="item1",
    title="Python Asyncio Best Practices",
    snippet="Guide to asyncio event loops and tasks in Python.",
    url="https://example.com/python-asyncio",
    metadata=None,
):
    return ResearchResult(
        id=f"job1_{source_item_id}",
        job_id="job1",
        source_name=source_name,
        source_item_id=source_item_id,
        title=title,
        content_snippet=snippet,
        source_url=url,
        content_type="article",
        metadata_fields=metadata or {},
    )


class _FakeStreamResponse:
    def __init__(self, status_code: int, url: str, body: bytes, content_type: str = "text/html; charset=utf-8"):
        self.status_code = status_code
        self.url = url
        self._body = body
        self.headers = {"content-type": content_type}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def aiter_bytes(self, chunk_size=16384):
        if self._body:
            yield self._body


def _mock_client(head_status=200, get_resp=None, get_json_map=None, head_exc=None):
    client = AsyncMock(spec=httpx.AsyncClient)

    if get_resp is None:
        get_resp = _FakeStreamResponse(head_status, "https://example.com", b"")

    def _stream(method, url, **kwargs):
        if head_exc:
            class _ErrCtx:
                async def __aenter__(self):
                    raise head_exc
                async def __aexit__(self, *args):
                    return False
            return _ErrCtx()
        return get_resp

    async def _get(url, **kwargs):
        if get_json_map:
            for prefix, (sc, payload) in get_json_map.items():
                if prefix in str(url):
                    r = MagicMock()
                    r.status_code = sc
                    r.url = url
                    r.json.return_value = payload
                    r.text = str(payload)
                    return r
        r = MagicMock()
        r.status_code = 404
        r.url = url
        r.json.return_value = None
        return r

    client.get = AsyncMock(side_effect=_get)
    client.stream = MagicMock(side_effect=_stream)
    return client


@pytest.mark.asyncio
async def test_1_valid_accessible_article():
    html = b"""
    <html><head>
      <title>Python Asyncio Best Practices - DevBlog</title>
      <link rel="canonical" href="https://example.com/python-asyncio" />
    </head><body>
      <h1>Python Asyncio Best Practices</h1>
      <p>Comprehensive guide to asyncio event loops, coroutines, and tasks in Python 3.12.</p>
    </body></html>
    """
    client = _mock_client(head_status=200, get_resp=_FakeStreamResponse(200, "https://example.com/python-asyncio", html))
    item = _make_result()
    outcome = await ResultValidator.validate_result(item, client)
    assert outcome.status == STATUS_VERIFIED
    assert item.validation_status == STATUS_VERIFIED
    assert item.canonical_url == "https://example.com/python-asyncio"
    assert item.http_status == 200


@pytest.mark.asyncio
async def test_2_valid_discussion_hn():
    client = _mock_client(
        get_json_map={
            "hacker-news.firebaseio.com/v0/item/12345.json": (
                200,
                {"id": 12345, "type": "story", "title": "Ask HN: Best Python tools?"},
            )
        }
    )
    item = _make_result(
        source_name="hackernews",
        source_item_id="12345",
        title="Ask HN: Best Python tools?",
        url="https://news.ycombinator.com/item?id=12345",
    )
    outcome = await ResultValidator.validate_result(item, client)
    assert outcome.status == STATUS_VERIFIED
    assert outcome.method == "hn_firebase_api"
    assert item.canonical_url == "https://news.ycombinator.com/item?id=12345"


@pytest.mark.asyncio
async def test_3_deleted_post_hn():
    client = _mock_client(
        get_json_map={
            "hacker-news.firebaseio.com/v0/item/99999.json": (
                200,
                {"id": 99999, "deleted": True},
            )
        }
    )
    item = _make_result(
        source_name="hackernews",
        source_item_id="99999",
        title="Deleted HN Story",
        url="https://news.ycombinator.com/item?id=99999",
    )
    outcome = await ResultValidator.validate_result(item, client)
    assert outcome.status == STATUS_DELETED
    assert item.validation_status == STATUS_DELETED


@pytest.mark.asyncio
async def test_4_genuine_404_url():
    client = _mock_client(head_status=404)
    item = _make_result(url="https://example.com/missing-page")
    outcome = await ResultValidator.validate_result(item, client)
    assert outcome.status == STATUS_NOT_FOUND
    assert outcome.http_status == 404


@pytest.mark.asyncio
async def test_5_410_gone_url():
    client = _mock_client(head_status=410)
    item = _make_result(url="https://example.com/removed-forever")
    outcome = await ResultValidator.validate_result(item, client)
    assert outcome.status == STATUS_NOT_FOUND
    assert outcome.http_status == 410


@pytest.mark.asyncio
async def test_6_redirect_preserves_final_and_canonical():
    html = b"""
    <html><head>
      <title>Python Asyncio Best Practices</title>
      <link rel="canonical" href="https://docs.example.com/v2/python-asyncio" />
    </head><body><p>Updated guide to Python asyncio event loops and tasks.</p></body></html>
    """
    client = _mock_client(
        head_status=200,
        get_resp=_FakeStreamResponse(200, "https://docs.example.com/v2/python-asyncio", html),
    )
    item = _make_result(url="https://example.com/old-asyncio-link")
    outcome = await ResultValidator.validate_result(item, client)
    assert outcome.status == STATUS_VERIFIED
    assert item.final_url == "https://docs.example.com/v2/python-asyncio"
    assert item.canonical_url == "https://docs.example.com/v2/python-asyncio"


@pytest.mark.asyncio
async def test_7_soft_404_detection():
    html = b"""
    <html><head><title>404 Page Not Found</title></head>
    <body><h1>Page Not Found</h1><p>Sorry, the page you requested could not be found.</p></body></html>
    """
    client = _mock_client(head_status=200, get_resp=_FakeStreamResponse(200, "https://example.com/soft404", html))
    item = _make_result(url="https://example.com/soft404")
    outcome = await ResultValidator.validate_result(item, client)
    assert outcome.status == STATUS_NOT_FOUND
    assert "Soft 404" in (outcome.reason or "")


@pytest.mark.asyncio
async def test_8_captcha_response_is_inaccessible_not_deleted():
    html = b"""
    <html><head><title>Just a moment...</title></head>
    <body><script>window._cf_chl_opt = {};</script>Enable JavaScript and cookies to continue.</body></html>
    """
    client = _mock_client(head_status=200, get_resp=_FakeStreamResponse(200, "https://example.com/protected", html))
    item = _make_result(url="https://example.com/protected")
    outcome = await ResultValidator.validate_result(item, client)
    assert outcome.status == STATUS_INACCESSIBLE
    assert outcome.status != STATUS_DELETED


@pytest.mark.asyncio
async def test_9_http_200_empty_content():
    html = b"<html><head><title></title></head><body>   </body></html>"
    client = _mock_client(head_status=200, get_resp=_FakeStreamResponse(200, "https://example.com/empty", html))
    item = _make_result(url="https://example.com/empty")
    outcome = await ResultValidator.validate_result(item, client)
    assert outcome.status == STATUS_MISMATCH
    assert "empty" in (outcome.reason or "").lower()


@pytest.mark.asyncio
async def test_10_valid_api_record_with_inaccessible_external_url():
    client = _mock_client(
        head_status=403,
        get_resp=_FakeStreamResponse(403, "https://publisher.example.com/paper/1", b"Forbidden"),
        get_json_map={
            "api.crossref.org/works/10.1000/test-doi": (200, {"status": "ok", "message": {"DOI": "10.1000/test-doi"}})
        },
    )
    item = _make_result(
        source_name="openalex",
        source_item_id="W123",
        title="Attention Is All You Need",
        url="https://publisher.example.com/paper/1",
        metadata={"doi": "10.1000/test-doi"},
    )
    outcome = await ResultValidator.validate_result(item, client)
    assert outcome.status == STATUS_PARTIALLY_VERIFIED
    assert "403" in (outcome.reason or "") or "inaccessible" in (outcome.reason or "").lower()


@pytest.mark.asyncio
async def test_11_temporarily_unavailable_server():
    client = _mock_client(head_exc=httpx.ConnectTimeout("timed out"))
    item = _make_result(url="https://slow.example.com/article")
    outcome = await ResultValidator.validate_result(item, client)
    assert outcome.status == STATUS_INACCESSIBLE
    assert outcome.method == "http_timeout"


@pytest.mark.asyncio
async def test_12_content_mismatch_with_original_source():
    html = b"""
    <html><head><title>Best Chocolate Cake Recipe</title></head>
    <body><h1>Grandma's Chocolate Cake</h1>
    <p>Mix flour, cocoa powder, sugar, eggs, and butter. Bake at 350 degrees for 30 minutes.</p></body></html>
    """
    client = _mock_client(head_status=200, get_resp=_FakeStreamResponse(200, "https://example.com/cake", html))
    item = _make_result(
        title="Quantum Cryptography Standards 2026",
        snippet="NIST post-quantum lattice encryption algorithms.",
        url="https://example.com/cake",
    )
    outcome = await ResultValidator.validate_result(item, client)
    assert outcome.status == STATUS_MISMATCH


@pytest.mark.asyncio
async def test_validation_cache_hit_and_expiry():
    db = _make_db()
    html = b"<html><head><title>Python Asyncio Best Practices</title></head><body><p>Asyncio guide for Python developers.</p></body></html>"
    client = _mock_client(head_status=200, get_resp=_FakeStreamResponse(200, "https://example.com/cached", html))

    item1 = _make_result(url="https://example.com/cached")
    out1 = await ResultValidator.validate_result(item1, client, db=db)
    assert out1.status == STATUS_VERIFIED
    assert client.stream.call_count == 1

    # Second call should hit cache without making any HTTP request
    item2 = _make_result(source_item_id="item2", url="https://example.com/cached")
    out2 = await ResultValidator.validate_result(item2, client, db=db)
    assert out2.status == STATUS_VERIFIED
    assert out2.method.startswith("cache:")
    assert client.stream.call_count == 1

    # Expire cache entry -> should revalidate via network
    cache_row = db.query(ValidationCache).filter(ValidationCache.url_hash == _url_hash("https://example.com/cached")).first()
    cache_row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()

    item3 = _make_result(source_item_id="item3", url="https://example.com/cached")
    out3 = await ResultValidator.validate_result(item3, client, db=db)
    assert out3.status == STATUS_VERIFIED
    assert not out3.method.startswith("cache:")
    assert client.stream.call_count == 2
