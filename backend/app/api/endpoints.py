import uuid
import csv
import io
import json
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.database import ResearchJob, ResearchResult, ResearchReport, CollectionLog, ResultFeedback, WishlistItem
from app.schemas.research import (
    ResearchJobCreate, ResearchJobResponse, ResearchResultResponse,
    ResearchReportResponse, SourceInfo, CollectionLogResponse, SourceDiagnosticResponse,
    ResultFeedbackCreate, ResultFeedbackResponse, WishlistItemCreate, WishlistItemResponse
)
from app.connectors.registry import list_all_sources, get_connector
from app.services.coordinator import ResearchCoordinator
from app.pipeline.ranker import Ranker
from app.pipeline.normalizer import Normalizer

router = APIRouter()

@router.get("/health")
def health_check():
    return {"status": "ok", "service": "Multi-Source AI Research Engine"}

@router.get("/performance/stats")
def performance_stats():
    from app.core.cache import get_all_cache_stats
    from app.core.resilience import circuit_breakers
    return {
        "caches": get_all_cache_stats(),
        "circuit_breakers": circuit_breakers.snapshot(),
    }

@router.get("/sources", response_model=List[SourceInfo])
def get_sources():
    return list_all_sources()

@router.get("/sources/{source_id}/test", response_model=SourceDiagnosticResponse)
async def test_source_connection(source_id: str):
    """
    Run diagnostic test for a specific source connector (e.g. reddit).
    Returns real connectivity, authorization, and configuration status without exposing tokens.
    """
    conn = get_connector(source_id)
    if not conn:
        raise HTTPException(status_code=404, detail=f"Source connector '{source_id}' not found")

    if hasattr(conn, "test_connection"):
        diag = await conn.test_connection()
    else:
        health = conn.check_health()
        diag = {
            "configured": True,
            "authorized": True,
            "connected": health.get("status") == "operational",
            "status": health.get("status", "operational"),
            "message": health.get("message", "Connector operational"),
            "last_checked_at": datetime.now(timezone.utc).isoformat()
        }

    return {
        "source_id": source_id,
        **diag
    }

@router.post("/research", response_model=ResearchJobResponse)
def create_research_job(
    payload: ResearchJobCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    job_id = str(uuid.uuid4())
    job = ResearchJob(
        id=job_id,
        query=payload.query.strip(),
        mode=payload.mode or "general",
        status="pending",
        progress=0.0,
        selected_sources=payload.sources or [],
        filters=payload.filters or {},
        limit_per_source=payload.limit_per_source or 15,
        total_results_count=0
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Launch background research task
    background_tasks.add_task(ResearchCoordinator.run_pipeline, job_id, db)

    return job

@router.get("/research/history", response_model=List[ResearchJobResponse])
def get_research_history(limit: int = 20, db: Session = Depends(get_db)):
    jobs = db.query(ResearchJob).order_by(ResearchJob.created_at.desc()).limit(limit).all()
    return jobs

@router.delete("/research/history")
def clear_research_history(db: Session = Depends(get_db)):
    """Delete all research history jobs, reports, results, and logs."""
    db.query(ResearchJob).delete()
    db.commit()
    return {"status": "success", "message": "All research history cleared"}

@router.delete("/research/{job_id}")
def delete_research_job(job_id: str, db: Session = Depends(get_db)):
    """Delete a single research job and all associated results/reports."""
    job = db.query(ResearchJob).filter(ResearchJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Research job not found")
    db.delete(job)
    db.commit()
    return {"status": "success", "job_id": job_id, "message": "Research job deleted"}

@router.get("/research/{job_id}", response_model=ResearchJobResponse)
def get_research_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(ResearchJob).filter(ResearchJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Research job not found")
    return job

@router.post("/research/{job_id}/cancel")
def cancel_research_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(ResearchJob).filter(ResearchJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Research job not found")
    if job.status in ("pending", "running"):
        job.status = "cancelled"
        db.commit()
    return {"status": "cancelled", "job_id": job_id}

@router.get("/research/{job_id}/results", response_model=List[ResearchResultResponse])
def get_research_results(
    job_id: str,
    source: Optional[str] = None,
    content_type: Optional[str] = None,
    language: Optional[str] = None,
    verification_status: Optional[str] = None,
    academic_only: bool = False,
    open_access_only: bool = False,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    min_relevance: Optional[float] = 0.0,
    include_duplicates: bool = False,
    sort_by: str = Query("relevant", pattern="^(relevant|newest|oldest)$"),
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    query = db.query(ResearchResult).filter(ResearchResult.job_id == job_id)
    if not include_duplicates:
        query = query.filter(ResearchResult.is_duplicate == False)
    if source:
        query = query.filter(ResearchResult.source_name == source)
    if content_type:
        query = query.filter(ResearchResult.content_type == content_type)
    if min_relevance and min_relevance > 0:
        query = query.filter(ResearchResult.relevance_score >= min_relevance)

    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
            query = query.filter(ResearchResult.published_at >= dt_from)
        except Exception:
            pass
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
            query = query.filter(ResearchResult.published_at <= dt_to)
        except Exception:
            pass

    all_rows = query.all()

    # Apply metadata-based filters cleanly in memory (SQLite JSON portable)
    filtered: List[ResearchResult] = []
    for r in all_rows:
        meta = r.metadata_fields or {}
        if language and meta.get("language") != language:
            continue
        if verification_status and meta.get("validation_status") != verification_status:
            continue
        if academic_only and not meta.get("is_academic", False):
            continue
        if open_access_only and not meta.get("is_open_access", False):
            continue
        filtered.append(r)

    sorted_results = Ranker.sort_results(filtered, sort_by=sort_by)
    return sorted_results[offset : offset + limit]


@router.post("/research/{job_id}/results/{result_id}/feedback", response_model=ResultFeedbackResponse)
def submit_result_feedback(
    job_id: str,
    result_id: str,
    payload: ResultFeedbackCreate,
    db: Session = Depends(get_db)
):
    """Store user feedback for offline evaluation without corrupting global ranking."""
    result = db.query(ResearchResult).filter(
        ResearchResult.id == result_id,
        ResearchResult.job_id == job_id
    ).first()
    if not result:
        raise HTTPException(status_code=404, detail="Research result not found")

    fb = ResultFeedback(
        job_id=job_id,
        result_id=result_id,
        feedback_type=payload.feedback_type,
        comment=payload.comment,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


@router.get("/research/{job_id}/feedback", response_model=List[ResultFeedbackResponse])
def get_job_feedback(job_id: str, db: Session = Depends(get_db)):
    return db.query(ResultFeedback).filter(ResultFeedback.job_id == job_id).order_by(ResultFeedback.created_at.desc()).all()

@router.get("/research/{job_id}/logs", response_model=List[CollectionLogResponse])
def get_collection_logs(job_id: str, db: Session = Depends(get_db)):
    logs = db.query(CollectionLog).filter(CollectionLog.job_id == job_id).order_by(CollectionLog.created_at.asc()).all()
    return logs

@router.get("/research/{job_id}/report", response_model=ResearchReportResponse)
def get_research_report(job_id: str, db: Session = Depends(get_db)):
    report = db.query(ResearchReport).filter(ResearchReport.job_id == job_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not generated yet or job still in progress")
    return report

@router.get("/research/{job_id}/export")
def export_research_results(
    job_id: str,
    format: str = Query("csv", pattern="^(csv|json)$"),
    db: Session = Depends(get_db)
):
    results = db.query(ResearchResult).filter(
        ResearchResult.job_id == job_id,
        ResearchResult.is_duplicate == False
    ).order_by(ResearchResult.relevance_score.desc()).all()

    if format == "json":
        data = [
            {
                "id": r.id,
                "source_name": r.source_name,
                "title": r.title,
                "source_url": r.source_url,
                "snippet": r.content_snippet,
                "author": r.author,
                "published_at": r.published_at.isoformat() if r.published_at else None,
                "relevance_score": r.relevance_score,
                "engagement_metrics": r.engagement_metrics
            }
            for r in results
        ]
        return StreamingResponse(
            io.StringIO(json.dumps(data, indent=2)),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=research_{job_id}.json"}
        )

    # CSV format
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Title", "Source", "URL", "Relevance Score", "Author", "Published At", "Snippet"])
    for r in results:
        writer.writerow([
            r.title,
            r.source_name,
            r.source_url,
            r.relevance_score,
            r.author or "",
            r.published_at.isoformat() if r.published_at else "",
            r.content_snippet or ""
        ])
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=research_{job_id}.csv"}
    )


# ── Research Wishlist Endpoints ───────────────────────────────────────────────

@router.get("/wishlist", response_model=List[WishlistItemResponse])
def get_wishlist_items(
    source: Optional[str] = None,
    content_type: Optional[str] = None,
    q: Optional[str] = None,
    sort_by: str = Query("saved_at", pattern="^(saved_at|relevance|newest|oldest)$"),
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    query = db.query(WishlistItem)
    if source:
        query = query.filter(WishlistItem.source_name == source)
    if content_type:
        query = query.filter(WishlistItem.content_type == content_type)
    items = query.all()

    if q and q.strip():
        q_low = q.strip().lower()
        items = [
            it for it in items
            if q_low in (it.title or "").lower() or q_low in (it.content_snippet or "").lower()
        ]

    if sort_by == "relevance":
        items.sort(key=lambda x: (-x.saved_relevance_score, x.id))
    elif sort_by == "newest":
        dated = [x for x in items if x.published_at is not None]
        undated = [x for x in items if x.published_at is None]
        dated.sort(key=lambda x: (-x.published_at.timestamp(), x.id))
        items = dated + undated
    elif sort_by == "oldest":
        dated = [x for x in items if x.published_at is not None]
        undated = [x for x in items if x.published_at is None]
        dated.sort(key=lambda x: (x.published_at.timestamp(), x.id))
        items = dated + undated
    else:
        items.sort(key=lambda x: (-(x.saved_at.timestamp() if x.saved_at else 0.0), x.id))

    return items[offset : offset + limit]


@router.post("/wishlist", response_model=WishlistItemResponse)
def add_wishlist_item(payload: WishlistItemCreate, db: Session = Depends(get_db)):
    canon = Normalizer.canonical_url(payload.canonical_url or payload.source_url)
    existing = db.query(WishlistItem).filter(WishlistItem.canonical_url == canon).first()
    if existing:
        # Prevent duplicates: return existing saved item cleanly
        return existing

    import hashlib
    item_id = hashlib.sha256(canon.encode("utf-8")).hexdigest()[:24]
    norm_pub = Normalizer.normalize_datetime(payload.published_at)

    item = WishlistItem(
        id=item_id,
        result_id=payload.result_id,
        job_id=payload.job_id,
        source_name=payload.source_name,
        source_item_id=payload.source_item_id,
        title=Normalizer.clean_text(payload.title),
        content_snippet=Normalizer.clean_text(payload.content_snippet) if payload.content_snippet else None,
        source_url=payload.source_url,
        canonical_url=canon,
        author=Normalizer.clean_text(payload.author) if payload.author else None,
        content_type=payload.content_type or "article",
        published_at=norm_pub,
        saved_relevance_score=payload.saved_relevance_score,
        validation_status=payload.validation_status or "UNCHECKED",
        metadata_fields=payload.metadata_fields or {},
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/wishlist/{item_id}")
def delete_wishlist_item(item_id: str, db: Session = Depends(get_db)):
    item = db.query(WishlistItem).filter(WishlistItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Wishlist item not found")
    db.delete(item)
    db.commit()
    return {"status": "deleted", "id": item_id}


@router.post("/wishlist/{item_id}/verify", response_model=WishlistItemResponse)
async def verify_wishlist_item(item_id: str, db: Session = Depends(get_db)):
    """Re-verify a saved Wishlist item's source link status without losing the saved record."""
    from app.services.validator import ValidationService
    from app.core.resilience import get_shared_http_client

    item = db.query(WishlistItem).filter(WishlistItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Wishlist item not found")

    client = get_shared_http_client()
    outcome = await ValidationService.level2_lightweight_verify(item.source_url, client)
    new_status = outcome.get("validation_status", item.validation_status)
    item.validation_status = new_status
    meta = dict(item.metadata_fields or {})
    meta.update(outcome)
    item.metadata_fields = meta
    db.commit()
    db.refresh(item)
    return item
