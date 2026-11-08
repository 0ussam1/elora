from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.discovery import (
    DiscoveryChatRequest, DiscoveryChatResponse,
    DiscoverySearchRequest, DiscoverySearchResponse
)
from app.services.discovery import DiscoveryService

router = APIRouter(prefix="/discovery", tags=["discovery"])

@router.get("/status")
def get_discovery_status():
    """
    Check if AI Discovery Mode provider (Z.AI / GLM or OpenAI) is configured.
    Returns provider details without exposing keys.
    """
    return DiscoveryService.get_provider_status()

@router.post("/chat", response_model=DiscoveryChatResponse)
async def discovery_chat(payload: DiscoveryChatRequest):
    """
    Process a natural language user exploration message.
    Understands intent, detects language, asks single clarification if necessary,
    and returns a structured discovery search plan.
    """
    return await DiscoveryService.process_chat(payload)

@router.post("/search", response_model=DiscoverySearchResponse)
async def discovery_search(payload: DiscoverySearchRequest, db: Session = Depends(get_db)):
    """
    Execute an approved discovery plan across real ELORA connectors.
    Collects, normalizes, deduplicates, and ranks real results.
    """
    if not payload.queries:
        raise HTTPException(status_code=400, detail="At least one query must be provided to execute discovery search")

    return await DiscoveryService.execute_discovery_search(
        queries=payload.queries,
        sources=payload.sources,
        mode=payload.mode or "general",
        limit_per_source=payload.limit_per_source or 10,
        original_objective=payload.original_objective,
        db=db
    )
