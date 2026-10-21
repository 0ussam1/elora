import asyncio
import time
import logging
from typing import List
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.database import ResearchJob, ResearchResult, CollectionLog
from app.connectors.registry import CONNECTOR_REGISTRY, get_connector
from app.pipeline.normalizer import Normalizer
from app.pipeline.deduplicator import Deduplicator
from app.pipeline.ranker import Ranker
from app.pipeline.report_generator import ReportGenerator

logger = logging.getLogger(__name__)

class ResearchCoordinator:
    @classmethod
    async def run_pipeline(cls, job_id: str, db: Session):
        job = db.query(ResearchJob).filter(ResearchJob.id == job_id).first()
        if not job or job.status == "cancelled":
            return

        job.status = "running"
        job.progress = 10.0
        db.commit()

        # Determine target sources
        target_sources = job.selected_sources
        if not target_sources:
            target_sources = [
                "hackernews", "web_search", "github", "stackexchange", 
                "arxiv", "wikipedia", "internet_archive", "openalex", "crossref", "openlibrary"
            ]

        # Run connectors concurrently with safe error handling
        tasks = []
        source_names = []
        for sid in target_sources:
            conn = get_connector(sid)
            if conn:
                tasks.append(cls._collect_from_source(conn, job.query, job.limit_per_source, job.filters))
                source_names.append(sid)

        job.progress = 25.0
        db.commit()

        # Execute parallel data collection
        results_nested = await asyncio.gather(*tasks, return_exceptions=True)

        all_normalized_results: List[ResearchResult] = []
        total_sources_count = len(source_names)
        
        for idx, res in enumerate(results_nested):
            sname = source_names[idx]
            if isinstance(res, Exception):
                logger.error(f"Error in connector {sname}: {res}")
                log = CollectionLog(
                    job_id=job.id,
                    source_name=sname,
                    status="error",
                    message=f"Connector error: {str(res)}",
                    items_collected=0,
                    duration_ms=0
                )
                db.add(log)
            else:
                raw_items, duration_ms = res
                log = CollectionLog(
                    job_id=job.id,
                    source_name=sname,
                    status="success" if raw_items else "empty",
                    message=f"Retrieved {len(raw_items)} items successfully",
                    items_collected=len(raw_items),
                    duration_ms=duration_ms
                )
                db.add(log)

                for raw in raw_items:
                    norm = Normalizer.normalize(raw, job.id)
                    all_normalized_results.append(norm)

        job.progress = 60.0
        db.commit()

        # Pipeline: Deduplication
        deduped = Deduplicator.deduplicate(all_normalized_results)

        job.progress = 75.0
        db.commit()

        # Pipeline: Relevance Ranking (TF-IDF, query overlap, metrics)
        ranked = Ranker.rank(job.query, deduped, mode=job.mode)

        # Persistence: save results
        for r in ranked:
            db.add(r)
        
        job.total_results_count = len(ranked)
        job.progress = 85.0
        db.commit()

        # Pipeline: Report Generation
        report = ReportGenerator.generate(job.id, job.query, ranked)
        db.add(report)

        job.status = "completed"
        job.progress = 100.0
        job.completed_at = datetime.utcnow()
        db.commit()

    @staticmethod
    async def _collect_from_source(connector, query: str, limit: int, filters: dict):
        start = time.time()
        try:
            items = await connector.search(query, limit=limit, filters=filters)
            duration_ms = int((time.time() - start) * 1000)
            return items, duration_ms
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            raise e
