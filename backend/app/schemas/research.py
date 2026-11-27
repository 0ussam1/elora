from pydantic import BaseModel, HttpUrl, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime

class ResearchJobCreate(BaseModel):
    query: str = Field(..., min_length=3, max_length=500, description="Natural-language search query")
    sources: Optional[List[str]] = Field(default=None, description="List of source IDs to query. Empty means all enabled.")
    mode: Optional[str] = Field(default="general", description="general, technical, or problem_discovery")
    limit_per_source: Optional[int] = Field(default=15, ge=1, le=50)
    filters: Optional[Dict[str, Any]] = Field(default_factory=dict)

class ResearchResultResponse(BaseModel):
    id: str
    job_id: str
    source_name: str
    source_item_id: Optional[str] = None
    title: str
    content_snippet: Optional[str] = None
    source_url: str
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    collected_at: datetime
    content_type: str
    engagement_metrics: Dict[str, Any] = {}
    metadata_fields: Dict[str, Any] = {}
    relevance_score: float = 0.0
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class ResearchJobResponse(BaseModel):
    id: str
    query: str
    mode: str
    status: str
    progress: float
    selected_sources: List[str]
    limit_per_source: int
    total_results_count: int
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class SourceInfo(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    category: str
    is_enabled: bool
    requires_auth: bool
    auth_status: str
    supported_content_types: List[str]
    rate_limit_per_minute: int
    health_status: str
    message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class SourceDiagnosticResponse(BaseModel):
    source_id: str
    configured: bool
    authorized: bool
    connected: bool
    status: str
    message: str
    last_checked_at: str


class ResultFeedbackCreate(BaseModel):
    feedback_type: str = Field(
        ...,
        pattern="^(relevant|irrelevant|correct_match|incorrect_match|wrong_entity|wrong_version|wrong_topic|poor_score_relevant|inflated_score_irrelevant|duplicate|broken_link|incorrect_date|misleading_description)$",
    )
    comment: Optional[str] = Field(default=None, max_length=500)


class ResultFeedbackResponse(BaseModel):
    id: int
    job_id: str
    result_id: str
    feedback_type: str
    comment: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WishlistItemCreate(BaseModel):
    result_id: Optional[str] = None
    job_id: Optional[str] = None
    source_name: str
    source_item_id: Optional[str] = None
    title: str
    content_snippet: Optional[str] = None
    source_url: str
    canonical_url: Optional[str] = None
    author: Optional[str] = None
    content_type: str = "article"
    published_at: Optional[datetime] = None
    saved_relevance_score: float = 0.0
    validation_status: str = "UNCHECKED"
    metadata_fields: Dict[str, Any] = {}


class WishlistItemResponse(BaseModel):
    id: str
    result_id: Optional[str] = None
    job_id: Optional[str] = None
    source_name: str
    source_item_id: Optional[str] = None
    title: str
    content_snippet: Optional[str] = None
    source_url: str
    canonical_url: str
    author: Optional[str] = None
    content_type: str
    published_at: Optional[datetime] = None
    saved_relevance_score: float
    validation_status: str
    metadata_fields: Dict[str, Any] = {}
    saved_at: datetime

    model_config = ConfigDict(from_attributes=True)
    details: Optional[Dict[str, Any]] = None

class CollectionLogResponse(BaseModel):
    id: int
    source_name: str
    status: str
    message: str
    items_collected: int
    duration_ms: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ResearchReportResponse(BaseModel):
    id: str
    job_id: str
    executive_summary: str
    main_findings: List[Dict[str, Any]]
    recurring_problems: List[Dict[str, Any]]
    perspectives: List[Dict[str, Any]]
    existing_solutions: List[Dict[str, Any]]
    potential_opportunities: List[Dict[str, Any]]
    limitations: List[str]
    collection_stats: Dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
