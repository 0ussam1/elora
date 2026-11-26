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
from app.models.database import ResearchJob, ResearchResult, ResearchReport, CollectionLog
from app.schemas.research import (
    ResearchJobCreate, ResearchJobResponse, ResearchResultResponse,
    ResearchReportResponse, SourceInfo, CollectionLogResponse, SourceDiagnosticResponse
)
from app.connectors.registry import list_all_sources, get_connector
from app.services.coordinator import ResearchCoordinator

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
    min_relevance: Optional[float] = 0.0,
    include_duplicates: bool = False,
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
    if min_relevance > 0:
        query = query.filter(ResearchResult.relevance_score >= min_relevance)

    results = query.order_by(ResearchResult.relevance_score.desc()).offset(offset).limit(limit).all()
    return results

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
