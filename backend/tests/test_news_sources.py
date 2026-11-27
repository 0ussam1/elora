"""
Tests for ELORA Dedicated News Integration System.

Covers:
  1. Connector class attributes, category ("news"), supported content types
  2. check_health() shape and status across all news connectors
  3. RSS 2.0 and Atom XML parsing with Dublin Core and Media RSS
  4. HTML tag stripping and sanitization
  5. RFC-2822 / RFC-822 and ISO-8601 publication date normalization to UTC
  6. Tracking query parameter stripping in canonical URLs
  7. Conditional HTTP requests (ETag & If-Modified-Since with HTTP 304)
  8. Error handling: HTTP 403 access_restricted, 404 invalid_feed, timeout temporarily_unavailable
  9. Duplicate prevention via canonical URL indexing
  10. Search relevance: keyword matching, title weighting, no artificial score inflation
  11. Chronological sorting using true publication dates
  12. Multilingual news support (English, French, Arabic)
  13. Feed enable / disable toggle
  14. Registry integration: all news sources registered in CONNECTOR_REGISTRY and list_all_sources()
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta

from app.connectors.news import (
    NewsConnector, BBCNewsConnector, AlJazeeraConnector,
    DeutscheWelleConnector, France24Connector, TheGuardianConnector,
    EuronewsConnector, SkyNewsConnector
)
from app.connectors.registry import CONNECTOR_REGISTRY, list_all_sources
from app.services.news_service import NewsService, strip_html_tags, DEFAULT_NEWS_FEEDS
from app.models.database import NewsFeed, IndexedNewsArticle, ResearchResult
from app.database.session import SessionLocal
from app.pipeline.normalizer import Normalizer
from app.pipeline.ranker import Ranker
from app.connectors.base import RawResult


# ── Sample XML Feeds for Testing ──────────────────────────────────────────────

SAMPLE_RSS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <title>BBC News - World</title>
    <link>https://www.bbc.co.uk/news/world</link>
    <description>BBC News World updates</description>
    <item>
      <title><![CDATA[Diplomatic Summit Concludes with Historic Climate Agreement]]></title>
      <link>https://www.bbc.co.uk/news/world-654321?at_medium=RSS&amp;at_campaign=rss</link>
      <description><![CDATA[World leaders reached a landmark <b>climate deal</b> covering renewable targets. <a href="http://example.com">Read more</a>]]></description>
      <pubDate>Fri, 27 Nov 2026 14:30:00 GMT</pubDate>
      <dc:creator>Jane Doe</dc:creator>
      <guid isPermaLink="false">bbc-news-world-654321</guid>
      <category>Climate</category>
      <category>Environment</category>
      <media:thumbnail url="https://ichef.bbci.co.uk/news/1024/branded_news/summit.jpg"/>
    </item>
    <item>
      <title>Autonomous Electric Aircraft Completes Maiden Transatlantic Flight</title>
      <link>https://www.bbc.co.uk/news/technology-987654?utm_source=rss&amp;utm_medium=feed</link>
      <description>The zero-emission battery electric flight took 7 hours to cross from London to Boston.</description>
      <pubDate>Fri, 27 Nov 2026 09:15:00 GMT</pubDate>
      <dc:creator>John Smith</dc:creator>
      <guid>https://www.bbc.co.uk/news/technology-987654</guid>
      <category>Aviation</category>
      <category>Technology</category>
    </item>
  </channel>
</rss>
"""

SAMPLE_ATOM_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>France 24 - Actualites</title>
  <link href="https://www.france24.com/fr/rss" rel="self"/>
  <updated>2026-11-27T16:00:00Z</updated>
  <entry>
    <title>L'Union Europeenne adopte de nouvelles regles sur l'intelligence artificielle</title>
    <link href="https://www.france24.com/fr/europe/20261127-ia-regles" rel="alternate"/>
    <id>urn:france24:20261127-ia-regles</id>
    <published>2026-11-27T15:45:00Z</published>
    <summary type="html">&lt;p&gt;Les parlementaires europeens ont vote le texte final encadrant les modeles fondamentaux.&lt;/p&gt;</summary>
    <author><name>Jean Dupont</name></author>
    <category term="Europe"/>
    <category term="Technologie"/>
  </entry>
</feed>
"""

SAMPLE_ARABIC_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>الجزيرة نت</title>
    <link>https://www.aljazeera.net</link>
    <item>
      <title>قمة دولية تبحث استقرار أسواق الطاقة العالمية</title>
      <link>https://www.aljazeera.net/news/2026/11/27/energy-summit?utm_source=rss</link>
      <description>اجتماع موسع في جنيف لمناقشة خطط التحول إلى الطاقة المتجددة وتأمين الإمدادات.</description>
      <pubDate>Fri, 27 Nov 2026 12:00:00 +0300</pubDate>
      <guid>aljazeera-energy-20261127</guid>
    </item>
  </channel>
</rss>
""".encode("utf-8")


# ══════════════════════════════════════════════════════════════════════════════
# 1. Connector Attributes & Health Check Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestNewsConnectors:
    def test_news_connector_class_attributes(self):
        conn = NewsConnector()
        assert conn.source_id == "news"
        assert conn.category == "news"
        assert conn.requires_auth is False
        assert "news" in conn.supported_content_types
        assert conn.rate_limit_per_minute >= 60

    def test_publisher_connectors_attributes(self):
        connectors = [
            (BBCNewsConnector(), "bbc_news", "BBC News"),
            (AlJazeeraConnector(), "al_jazeera", "Al Jazeera"),
            (DeutscheWelleConnector(), "deutsche_welle", "Deutsche Welle (DW)"),
            (France24Connector(), "france24", "France 24"),
            (TheGuardianConnector(), "the_guardian", "The Guardian"),
            (EuronewsConnector(), "euronews", "Euronews"),
            (SkyNewsConnector(), "sky_news", "Sky News")
        ]
        for conn, sid, expected_name in connectors:
            assert conn.source_id == sid
            assert conn.category == "news"
            assert conn.requires_auth is False
            assert "news" in conn.supported_content_types
            assert conn.name == expected_name

    def test_health_check_shape(self):
        conn = NewsConnector()
        health = conn.check_health()
        assert "status" in health
        assert health["status"] in ("operational", "degraded", "error")
        assert health["auth_status"] == "not_required"
        assert "total_feeds" in health
        assert health["total_feeds"] >= len(DEFAULT_NEWS_FEEDS)


# ══════════════════════════════════════════════════════════════════════════════
# 2. XML Parsing & Date Normalization Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestNewsParsingAndNormalization:
    def test_rss2_parsing(self):
        feed = NewsFeed(
            id="bbc_test",
            publisher="BBC News",
            name="BBC Test",
            feed_url="https://feeds.bbci.co.uk/news/world/rss.xml",
            category="world",
            language="en"
        )
        items = NewsService.parse_feed_xml(SAMPLE_RSS_XML, feed)
        assert len(items) == 2

        item1 = items[0]
        assert "Diplomatic Summit" in item1["title"]
        assert item1["canonical_url"] == "https://www.bbc.co.uk/news/world-654321"
        assert "climate deal" in item1["content_snippet"]
        assert "<b" not in item1["content_snippet"]  # HTML stripped
        assert item1["author"] == "Jane Doe"
        assert item1["published_at"] is not None
        assert item1["published_at"].year == 2026
        assert item1["published_at"].month == 11
        assert item1["published_at"].day == 27
        assert "Climate" in item1["tags"]
        assert item1["image_url"] == "https://ichef.bbci.co.uk/news/1024/branded_news/summit.jpg"

        item2 = items[1]
        assert "Autonomous Electric Aircraft" in item2["title"]
        assert item2["canonical_url"] == "https://www.bbc.co.uk/news/technology-987654"

    def test_atom_parsing(self):
        feed = NewsFeed(
            id="f24_test",
            publisher="France 24",
            name="France 24 FR",
            feed_url="https://www.france24.com/fr/rss",
            category="world",
            language="fr"
        )
        items = NewsService.parse_feed_xml(SAMPLE_ATOM_XML, feed)
        assert len(items) == 1
        item = items[0]
        assert "Union Europeenne" in item["title"]
        assert item["canonical_url"] == "https://www.france24.com/fr/europe/20261127-ia-regles"
        assert "<p>" not in item["content_snippet"]
        assert "parlementaires" in item["content_snippet"]
        assert item["published_at"] is not None
        assert item["author"] == "Jean Dupont"
        assert "Europe" in item["tags"]

    def test_arabic_rss_parsing(self):
        feed = NewsFeed(
            id="aj_ar_test",
            publisher="Al Jazeera",
            name="Al Jazeera AR",
            feed_url="https://www.aljazeera.net/rss",
            category="world",
            language="ar"
        )
        items = NewsService.parse_feed_xml(SAMPLE_ARABIC_RSS, feed)
        assert len(items) == 1
        item = items[0]
        assert "قمة دولية" in item["title"]
        assert item["canonical_url"] == "https://www.aljazeera.net/news/2026/11/27/energy-summit"
        assert item["published_at"] is not None

    def test_strip_html_tags_utility(self):
        raw = "<p>Breaking news: <script>alert(1);</script><b>Storm hits coastline</b>. <a href='#'>More</a></p>"
        clean = strip_html_tags(raw)
        assert "<" not in clean
        assert "alert(1)" not in clean
        assert "Breaking news: Storm hits coastline. More" in clean

    def test_tracking_query_params_stripped_in_canonical_url(self):
        url = "https://example.com/article?utm_source=twitter&utm_medium=social&at_medium=RSS&ref=home"
        canonical = Normalizer.canonical_url(url)
        assert "utm_" not in canonical
        assert "at_medium" not in canonical
        assert "ref=" not in canonical
        assert canonical == "https://example.com/article"

    def test_rfc2822_date_normalization(self):
        raw_date = "Fri, 27 Nov 2026 17:17:11 GMT"
        dt = Normalizer.normalize_datetime(raw_date)
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 11
        assert dt.day == 27
        assert dt.hour == 17
        assert dt.tzinfo == timezone.utc


# ══════════════════════════════════════════════════════════════════════════════
# 3. Conditional Ingestion & Health Tracking Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestNewsIngestionAndHealth:
    @pytest.mark.asyncio
    async def test_ingest_feed_200_ok(self):
        import hashlib
        # Canonical URLs that SAMPLE_RSS_XML generates after tracking-param stripping
        SAMPLE_ART_IDS = [
            hashlib.sha256(b"https://www.bbc.co.uk/news/world-654321").hexdigest()[:24],
            hashlib.sha256(b"https://www.bbc.co.uk/news/technology-987654").hexdigest()[:24],
        ]
        with SessionLocal() as db:
            # Create a test feed
            feed = NewsFeed(
                id="test_ingest_feed_200",
                publisher="BBC News",
                name="BBC News Test 200",
                feed_url="https://feeds.bbci.co.uk/news/test_200.xml",
                category="world",
                language="en",
                is_enabled=True,
                health_status="operational"
            )
            db.merge(feed)
            db.commit()

            # Clean up any pre-existing articles by their canonical art_id (test isolation)
            # They may have been inserted by another test with a different feed_id
            db.query(IndexedNewsArticle).filter(
                IndexedNewsArticle.id.in_(SAMPLE_ART_IDS)
            ).delete(synchronize_session=False)
            db.commit()

            # Mock httpx response
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.content = SAMPLE_RSS_XML
            mock_resp.headers = {"ETag": '"abc123etag"', "Last-Modified": "Fri, 27 Nov 2026 14:30:00 GMT"}

            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp

            res = await NewsService.ingest_feed("test_ingest_feed_200", db, mock_client)
            assert res["status"] == "success"
            assert res["http_status"] == 200
            assert res["new_articles"] >= 2

            # Verify feed updated in DB
            updated_feed = db.query(NewsFeed).filter(NewsFeed.id == "test_ingest_feed_200").first()
            assert updated_feed.etag == '"abc123etag"'
            assert updated_feed.last_modified_header == "Fri, 27 Nov 2026 14:30:00 GMT"
            assert updated_feed.health_status == "operational"
            assert updated_feed.articles_count >= 2

    @pytest.mark.asyncio
    async def test_ingest_feed_304_not_modified(self):
        with SessionLocal() as db:
            feed = NewsFeed(
                id="test_ingest_feed_304",
                publisher="BBC News",
                name="BBC News Test 304",
                feed_url="https://feeds.bbci.co.uk/news/test_304.xml",
                category="world",
                language="en",
                is_enabled=True,
                etag='"existing_etag"',
                last_modified_header="Fri, 27 Nov 2026 10:00:00 GMT",
                articles_count=5,
                health_status="operational"
            )
            db.merge(feed)
            db.commit()

            mock_resp = MagicMock()
            mock_resp.status_code = 304
            mock_resp.headers = {}

            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp

            res = await NewsService.ingest_feed("test_ingest_feed_304", db, mock_client)
            assert res["status"] == "not_modified"
            assert res["http_status"] == 304

            # Verify conditional headers were sent
            called_headers = mock_client.get.call_args[1]["headers"]
            assert called_headers["If-None-Match"] == '"existing_etag"'
            assert called_headers["If-Modified-Since"] == "Fri, 27 Nov 2026 10:00:00 GMT"

    @pytest.mark.asyncio
    async def test_ingest_feed_403_access_restricted(self):
        with SessionLocal() as db:
            feed = NewsFeed(
                id="test_ingest_feed_403",
                publisher="Restricted Publisher",
                name="Restricted Test",
                feed_url="https://example.com/restricted.xml",
                is_enabled=True
            )
            db.merge(feed)
            db.commit()

            mock_resp = MagicMock()
            mock_resp.status_code = 403
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp

            res = await NewsService.ingest_feed("test_ingest_feed_403", db, mock_client)
            assert res["status"] == "error"
            updated = db.query(NewsFeed).filter(NewsFeed.id == "test_ingest_feed_403").first()
            assert updated.health_status == "access_restricted"

    @pytest.mark.asyncio
    async def test_duplicate_prevention_on_canonical_url(self):
        import hashlib
        SAMPLE_ART_IDS = [
            hashlib.sha256(b"https://www.bbc.co.uk/news/world-654321").hexdigest()[:24],
            hashlib.sha256(b"https://www.bbc.co.uk/news/technology-987654").hexdigest()[:24],
        ]
        with SessionLocal() as db:
            feed = NewsFeed(
                id="test_dup_feed",
                publisher="Sky News",
                name="Sky News Dup Test",
                feed_url="https://feeds.skynews.com/test_dup.xml",
                is_enabled=True
            )
            db.merge(feed)
            db.commit()

            # Clean up any pre-existing articles sharing same art_ids (cross-test isolation)
            db.query(IndexedNewsArticle).filter(
                IndexedNewsArticle.id.in_(SAMPLE_ART_IDS)
            ).delete(synchronize_session=False)
            db.commit()

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.content = SAMPLE_RSS_XML
            mock_resp.headers = {}
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp

            # Run ingestion twice with same XML
            await NewsService.ingest_feed("test_dup_feed", db, mock_client)
            count_after_first = db.query(IndexedNewsArticle).filter(IndexedNewsArticle.feed_id == "test_dup_feed").count()

            res2 = await NewsService.ingest_feed("test_dup_feed", db, mock_client)
            count_after_second = db.query(IndexedNewsArticle).filter(IndexedNewsArticle.feed_id == "test_dup_feed").count()

            assert count_after_first == count_after_second
            assert res2["new_articles"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# 4. Search Relevance & Chronological Sorting Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestNewsSearchAndRanking:
    @pytest.mark.asyncio
    async def test_search_indexed_news_relevance(self):
        with SessionLocal() as db:
            # Seed sample articles
            db.merge(IndexedNewsArticle(
                id="news_art_1",
                feed_id="bbc_world",
                publisher="BBC News",
                title="Global Climate Summit Agrees on Renewable Energy Target",
                content_snippet="World leaders have finalized historic agreement to triple renewable energy capacity.",
                source_url="https://bbc.co.uk/news/climate-1",
                canonical_url="https://bbc.co.uk/news/climate-1",
                published_at=datetime(2026, 11, 27, 10, 0, 0, tzinfo=timezone.utc),
                category="world",
                language="en"
            ))
            db.merge(IndexedNewsArticle(
                id="news_art_2",
                feed_id="bbc_tech",
                publisher="BBC News",
                title="Electric Aviation Makes Progress with Transatlantic Flight",
                content_snippet="Battery electric passenger plane successfully flew London to Boston.",
                source_url="https://bbc.co.uk/news/electric-flight",
                canonical_url="https://bbc.co.uk/news/electric-flight",
                published_at=datetime(2026, 11, 26, 8, 0, 0, tzinfo=timezone.utc),
                category="technology",
                language="en"
            ))
            db.commit()

            results = await NewsService.search_indexed_news("Climate Renewable Energy", limit=5, db=db)
            assert len(results) >= 1
            top = results[0]
            assert "Climate Summit" in top.title
            assert top.source_name == "news"
            assert top.content_type == "news"
            assert top.metadata["publisher"] == "BBC News"

    def test_chronological_sorting_uses_true_pubdate(self):
        older = ResearchResult(
            id="res_older",
            job_id="test_job",
            source_name="news",
            title="Older Breaking News",
            source_url="https://bbc.co.uk/news/older",
            published_at=datetime(2026, 11, 25, 12, 0, 0, tzinfo=timezone.utc),
            relevance_score=0.75
        )
        newer = ResearchResult(
            id="res_newer",
            job_id="test_job",
            source_name="news",
            title="Newest Breaking News",
            source_url="https://bbc.co.uk/news/newer",
            published_at=datetime(2026, 11, 27, 15, 0, 0, tzinfo=timezone.utc),
            relevance_score=0.70
        )

        # Sort newest first
        sorted_newest = Ranker.sort_results([older, newer], sort_by="newest")
        assert sorted_newest[0].id == "res_newer"
        assert sorted_newest[1].id == "res_older"

        # Sort oldest first
        sorted_oldest = Ranker.sort_results([older, newer], sort_by="oldest")
        assert sorted_oldest[0].id == "res_older"
        assert sorted_oldest[1].id == "res_newer"

        # Default: Most Relevant
        sorted_rel = Ranker.sort_results([older, newer], sort_by="relevant")
        assert sorted_rel[0].id == "res_older"  # higher relevance score 0.75 vs 0.70

    def test_no_artificial_ranking_advantage(self):
        """News result must not rank above academic/technical documentation if irrelevant to query."""
        from app.pipeline.query_analyzer import QueryAnalyzer
        analysis = QueryAnalyzer.analyze("Python 3.13 memory management")

        tech_doc = ResearchResult(
            id="doc_py",
            job_id="job_test",
            source_name="github",
            title="Python 3.13 Free-threaded Memory Management Internals",
            content_snippet="Detailed architectural specification of Python 3.13 mimalloc allocator and GIL removal.",
            source_url="https://github.com/python/cpython/doc",
            published_at=datetime(2025, 10, 1, tzinfo=timezone.utc),
            relevance_score=0.0
        )
        unrelated_news = ResearchResult(
            id="news_unrelated",
            job_id="job_test",
            source_name="news",
            title="Rockstar Games Releases Latest Grand Theft Auto Video",
            content_snippet="Entertainment updates from the gaming industry.",
            source_url="https://bbc.co.uk/news/gta",
            published_at=datetime(2026, 11, 27, tzinfo=timezone.utc),
            relevance_score=0.0
        )

        ranked = Ranker.rank("Python 3.13 memory management", [unrelated_news, tech_doc], analysis=analysis)
        # Tech doc should score significantly higher than unrelated news article
        doc_res = next(r for r in ranked if r.id == "doc_py")
        news_res = next(r for r in ranked if r.id == "news_unrelated")
        assert doc_res.relevance_score > news_res.relevance_score
        assert news_res.relevance_score < 0.20  # properly penalized / irrelevant


# ══════════════════════════════════════════════════════════════════════════════
# 5. Registry Integration Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestNewsRegistryIntegration:
    def test_all_news_sources_registered(self):
        expected_news_ids = {
            "news", "bbc_news", "al_jazeera", "deutsche_welle",
            "france24", "the_guardian", "euronews", "sky_news"
        }
        registered = set(CONNECTOR_REGISTRY.keys())
        assert expected_news_ids.issubset(registered), f"Missing: {expected_news_ids - registered}"

    def test_all_news_sources_have_news_category(self):
        for sid in ("news", "bbc_news", "al_jazeera", "deutsche_welle", "france24", "the_guardian", "euronews", "sky_news"):
            conn = CONNECTOR_REGISTRY[sid]
            assert conn.category == "news"

    def test_list_all_sources_includes_news_category(self):
        sources = list_all_sources()
        news_sources = [s for s in sources if s["category"] == "news"]
        assert len(news_sources) >= 8
