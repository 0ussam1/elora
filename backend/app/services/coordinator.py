import asyncio
import hashlib
import json
import time
import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.cache import search_cache
from app.core.resilience import circuit_breakers
from app.models.database import ResearchJob, ResearchResult, CollectionLog
from app.connectors.registry import get_connector
from app.pipeline.normalizer import Normalizer
from app.pipeline.deduplicator import Deduplicator
from app.pipeline.query_analyzer import QueryAnalyzer
from app.pipeline.ranker import Ranker
from app.pipeline.report_generator import ReportGenerator
from app.services.validator import ValidationService

logger = logging.getLogger(__name__)


def _make_search_cache_key(source_id: str, query: str, limit: int, filters: Optional[dict]) -> str:
    raw = json.dumps(
        {"s": source_id, "q": query.strip().lower(), "l": limit, "f": filters or {}},
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ResearchCoordinator:
    @classmethod
    async def run_pipeline(cls, job_id: str, db: Session):
        job = db.query(ResearchJob).filter(ResearchJob.id == job_id).first()
        if not job or job.status == "cancelled":
            return

        job.status = "running"
        job.progress = 10.0
        db.commit()

        # Analyze query intent, entities, versions, language & multilingual concepts
        query_analysis = QueryAnalyzer.analyze(job.query)

        target_sources = job.selected_sources
        if not target_sources:
            target_sources = [
                "hackernews", "web_search", "github", "stackexchange",
                "arxiv", "wikipedia", "internet_archive", "openalex", "crossref", "openlibrary"
            ]

        sem = asyncio.Semaphore(settings.MAX_CONCURRENT_REQUESTS)

        async def _run_provider(sid: str):
            conn = get_connector(sid)
            if not conn:
                return sid, [], 0, "missing_connector", False
            return await cls._collect_from_source(
                conn, sid, job.query, job.limit_per_source, job.filters, sem
            )

        tasks = [asyncio.create_task(_run_provider(sid)) for sid in target_sources]
        total_sources = max(len(tasks), 1)
        completed_sources = 0

        job.progress = 20.0
        db.commit()

        all_normalized_results: List[ResearchResult] = []
        persisted_ids: set[str] = set()

        # Progressive collection: save partial results as fast providers finish
        for coro in asyncio.as_completed(tasks):
            try:
                sname, raw_items, duration_ms, status_tag, from_cache = await coro
            except Exception as exc:
                logger.error(f"Unexpected provider task error: {exc}")
                completed_sources += 1
                continue

            completed_sources += 1

            if status_tag.startswith("error:") or status_tag == "timeout" or status_tag == "circuit_open":
                log = CollectionLog(
                    job_id=job.id,
                    source_name=sname,
                    status="error" if status_tag != "circuit_open" else "warning",
                    message=(
                        "Circuit breaker open (provider skipped)"
                        if status_tag == "circuit_open"
                        else f"Provider {status_tag} after {duration_ms}ms"
                    ),
                    items_collected=0,
                    duration_ms=duration_ms,
                )
                db.add(log)
            else:
                cache_note = " (cached)" if from_cache else ""
                log = CollectionLog(
                    job_id=job.id,
                    source_name=sname,
                    status="success" if raw_items else "empty",
                    message=f"Retrieved {len(raw_items)} items{cache_note} in {duration_ms}ms",
                    items_collected=len(raw_items),
                    duration_ms=duration_ms,
                )
                db.add(log)

                new_batch: List[ResearchResult] = []
                for raw in raw_items:
                    norm = Normalizer.normalize(raw, job.id)
                    # Level 1 Fast Verification inline (<1ms, zero network)
                    l1 = ValidationService.level1_fast_verify(norm)
                    meta = dict(norm.metadata_fields or {})
                    meta.update(l1)
                    norm.metadata_fields = meta
                    all_normalized_results.append(norm)
                    if norm.id not in persisted_ids:
                        persisted_ids.add(norm.id)
                        new_batch.append(norm)

                # Progressive rank & flush so frontend sees fast providers immediately
                if new_batch:
                    Ranker.rank(job.query, new_batch, mode=job.mode, analysis=query_analysis)
                    db.add_all(new_batch)

            job.progress = round(20.0 + (completed_sources / total_sources) * 55.0, 1)
            job.total_results_count = len(persisted_ids)
            db.commit()

        # Final Deduplication & Ranking across all collected results
        deduped = Deduplicator.deduplicate(all_normalized_results)
        ranked = Ranker.rank(job.query, deduped, mode=job.mode, analysis=query_analysis)

        job.total_results_count = len(ranked)
        job.progress = 85.0
        db.commit()

        # Report Generation
        report = ReportGenerator.generate(job.id, job.query, ranked)
        stats = dict(report.collection_stats or {})
        stats["query_analysis"] = query_analysis.to_dict()
        report.collection_stats = stats
        db.add(report)

        job.status = "completed"
        job.progress = 100.0
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

        # Launch Level 2 & Level 3 validation asynchronously — NEVER blocks search
        try:
            asyncio.create_task(ValidationService.validate_job_results_async(job.id))
        except RuntimeError:
            pass

    @staticmethod
    async def _collect_from_source(
        connector,
        source_id: str,
        query: str,
        limit: int,
        filters: Optional[dict],
        sem: asyncio.Semaphore,
    ) -> Tuple[str, list, int, str, bool]:
        """
        Collect from a single provider with:
          1. Search cache lookup
          2. Circuit breaker check
          3. Bounded concurrency semaphore
          4. Per-provider timeout (PROVIDER_TIMEOUT_SECONDS)
        """
        cache_key = _make_search_cache_key(source_id, query, limit, filters)
        cached = search_cache.get(cache_key)
        if cached is not None:
            return source_id, cached, 0, "ok", True

        breaker = circuit_breakers.get(source_id)
        if not breaker.allow_request():
            return source_id, [], 0, "circuit_open", False

        start = time.perf_counter()
        try:
            async with sem:
                items = await asyncio.wait_for(
                    connector.search(query, limit=limit, filters=filters),
                    timeout=settings.PROVIDER_TIMEOUT_SECONDS,
                )
            duration_ms = int((time.perf_counter() - start) * 1000)
            breaker.record_success()
            search_cache.set(cache_key, items, ttl=settings.SEARCH_CACHE_TTL_SECONDS)
            return source_id, items, duration_ms, "ok", False
        except asyncio.TimeoutError:
            duration_ms = int((time.perf_counter() - start) * 1000)
            breaker.record_failure()
            logger.warning(f"Provider '{source_id}' timed out after {duration_ms}ms")
            return source_id, [], duration_ms, "timeout", False
        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            breaker.record_failure()
            logger.error(f"Provider '{source_id}' failed in {duration_ms}ms: {e}")
            return source_id, [], duration_ms, f"error:{type(e).__name__}", False
