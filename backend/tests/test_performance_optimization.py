"""
Performance & Validation Pipeline Tests for ELORA.

Covers:
  1. Concurrent search + progressive persistence
  2. Slow/timeout provider isolation (fast providers are not blocked)
  3. Circuit breaker opening after consecutive failures
  4. Search cache hit rate on repeated identical searches (0 external calls)
  5. Three-level intelligent validation (Level 1 fast, Level 2 lightweight, Level 3 deep soft-404)
  6. Never classifying unverified results as VERIFIED
"""
import asyncio
import time
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.models.database import ResearchJob, ResearchResult
from app.connectors.base import RawResult
from app.core.cache import (
    clear_all_caches, search_cache, url_validation_cache,
    deep_validation_cache, get_all_cache_stats
)
from app.core.resilience import circuit_breakers
from app.services.coordinator import ResearchCoordinator
from app.services.validator import ValidationService


@pytest.fixture
def mem_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def reset_state():
    clear_all_caches()
    circuit_breakers.reset_all()
    yield
    clear_all_caches()
    circuit_breakers.reset_all()


class FakeFastConnector:
    def __init__(self, sid: str, delay: float = 0.01):
        self.source_id = sid
        self.calls = 0
        self.delay = delay

    async def search(self, query: str, limit: int = 15, filters=None):
        self.calls += 1
        await asyncio.sleep(self.delay)
        return [
            RawResult(
                source_name=self.source_id,
                source_item_id=f"{self.source_id}-1",
                title=f"Result from {self.source_id} for {query}",
                content_snippet="Relevant research snippet.",
                source_url=f"https://example.org/{self.source_id}/1",
                content_type="article",
            )
        ]


class FakeFailingConnector:
    def __init__(self, sid: str):
        self.source_id = sid
        self.calls = 0

    async def search(self, query: str, limit: int = 15, filters=None):
        self.calls += 1
        raise RuntimeError("Simulated provider outage")


class FakeSlowConnector:
    def __init__(self, sid: str, delay: float = 5.0):
        self.source_id = sid
        self.calls = 0
        self.delay = delay

    async def search(self, query: str, limit: int = 15, filters=None):
        self.calls += 1
        await asyncio.sleep(self.delay)
        return []


@pytest.mark.asyncio
async def test_concurrent_search_and_cache_hit(mem_db):
    fast1 = FakeFastConnector("fast_a", delay=0.02)
    fast2 = FakeFastConnector("fast_b", delay=0.02)
    connectors = {"fast_a": fast1, "fast_b": fast2}

    with patch("app.services.coordinator.get_connector", side_effect=lambda sid: connectors.get(sid)), \
         patch("app.services.coordinator.ValidationService.validate_job_results_async", new_callable=AsyncMock):
        job1 = ResearchJob(
            id=str(uuid.uuid4()), query="async optimization", mode="general",
            selected_sources=["fast_a", "fast_b"], limit_per_source=5
        )
        mem_db.add(job1)
        mem_db.commit()

        t0 = time.perf_counter()
        await ResearchCoordinator.run_pipeline(job1.id, mem_db)
        first_ms = (time.perf_counter() - t0) * 1000

        assert job1.status == "completed"
        assert job1.total_results_count == 2
        assert fast1.calls == 1
        assert fast2.calls == 1

        # Second identical search must hit search_cache (0 new external calls)
        job2 = ResearchJob(
            id=str(uuid.uuid4()), query="async optimization", mode="general",
            selected_sources=["fast_a", "fast_b"], limit_per_source=5
        )
        mem_db.add(job2)
        mem_db.commit()

        t1 = time.perf_counter()
        await ResearchCoordinator.run_pipeline(job2.id, mem_db)
        cached_ms = (time.perf_counter() - t1) * 1000

        assert job2.status == "completed"
        assert job2.total_results_count == 2
        assert fast1.calls == 1  # No additional external call
        assert fast2.calls == 1
        stats = get_all_cache_stats()
        assert stats["search_cache"]["hits"] >= 2
        assert cached_ms <= first_ms + 50


@pytest.mark.asyncio
async def test_slow_provider_timeout_does_not_block_fast_providers(mem_db, monkeypatch):
    monkeypatch.setattr("app.services.coordinator.settings.PROVIDER_TIMEOUT_SECONDS", 0.15)
    fast = FakeFastConnector("fast_ok", delay=0.01)
    slow = FakeSlowConnector("slow_hang", delay=2.0)
    connectors = {"fast_ok": fast, "slow_hang": slow}

    with patch("app.services.coordinator.get_connector", side_effect=lambda sid: connectors.get(sid)), \
         patch("app.services.coordinator.ValidationService.validate_job_results_async", new_callable=AsyncMock):
        job = ResearchJob(
            id=str(uuid.uuid4()), query="timeout isolation", mode="general",
            selected_sources=["fast_ok", "slow_hang"], limit_per_source=5
        )
        mem_db.add(job)
        mem_db.commit()

        t0 = time.perf_counter()
        await ResearchCoordinator.run_pipeline(job.id, mem_db)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert job.status == "completed"
        assert job.total_results_count == 1  # Fast provider succeeded
        assert elapsed_ms < 1000  # Did NOT wait 2.0s for slow provider


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_repeated_failures(mem_db):
    failing = FakeFailingConnector("broken_src")
    connectors = {"broken_src": failing}

    with patch("app.services.coordinator.get_connector", side_effect=lambda sid: connectors.get(sid)), \
         patch("app.services.coordinator.ValidationService.validate_job_results_async", new_callable=AsyncMock):
        for i in range(3):
            j = ResearchJob(
                id=str(uuid.uuid4()), query=f"q-{i}", mode="general",
                selected_sources=["broken_src"], limit_per_source=5
            )
            mem_db.add(j)
            mem_db.commit()
            await ResearchCoordinator.run_pipeline(j.id, mem_db)

        assert failing.calls == 3
        assert circuit_breakers.get("broken_src").state == "open"

        # 4th call must skip immediately without calling connector.search()
        j4 = ResearchJob(
            id=str(uuid.uuid4()), query="q-4", mode="general",
            selected_sources=["broken_src"], limit_per_source=5
        )
        mem_db.add(j4)
        mem_db.commit()
        await ResearchCoordinator.run_pipeline(j4.id, mem_db)
        assert failing.calls == 3


class TestThreeLevelValidation:
    def test_level1_never_marks_verified_without_cache(self):
        r = ResearchResult(
            id="r1", job_id="j1", source_name="arxiv",
            source_item_id="2401.00001", title="Test Paper",
            source_url="https://arxiv.org/abs/2401.00001",
        )
        v = ValidationService.level1_fast_verify(r)
        assert v["validation_status"] == "FAST_VERIFIED"
        assert v["validation_status"] != "VERIFIED"
        assert v["validation_level"] == 1

    def test_level1_invalid_url_rejected(self):
        r = ResearchResult(
            id="r2", job_id="j1", source_name="web_search",
            title="Bad Link", source_url="not-a-valid-url",
        )
        v = ValidationService.level1_fast_verify(r)
        assert v["validation_status"] == "INVALID_URL"

    @pytest.mark.asyncio
    async def test_level2_detects_404_and_caches(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.url = "https://example.org/missing"
        mock_client = AsyncMock()
        mock_client.head = AsyncMock(return_value=mock_resp)

        res1 = await ValidationService.level2_lightweight_verify("https://example.org/missing", mock_client)
        assert res1["validation_status"] == "BROKEN_LINK"
        assert res1["http_status"] == 404

        # Second call hits url_validation_cache (head not called again)
        res2 = await ValidationService.level2_lightweight_verify("https://example.org/missing", mock_client)
        assert res2["validation_cached"] is True
        assert mock_client.head.call_count == 1

    @pytest.mark.asyncio
    async def test_level3_detects_soft_404(self):
        class FakeStreamResp:
            status_code = 200
            url = "https://example.org/soft404"
            headers = {"content-type": "text/html"}

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def aiter_bytes(self, chunk_size=4096):
                yield b"<html><head><title>404 Not Found - Page Missing</title></head><body>Oops</body></html>"

        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value=FakeStreamResp())

        res = await ValidationService.level3_deep_verify("https://example.org/soft404", "Real Document", mock_client)
        assert res["validation_status"] == "SOFT_404"
        assert res["soft_404_detected"] is True
        assert res["validation_level"] == 3
