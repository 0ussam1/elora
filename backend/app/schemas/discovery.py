from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from app.schemas.research import ResearchResultResponse

class DiscoveryChatMessage(BaseModel):
    role: str = Field(..., description="Role: 'user' or 'assistant'")
    content: str = Field(..., description="Message text")

class DiscoveryChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="User natural language request or response")
    history: List[DiscoveryChatMessage] = Field(default_factory=list, description="Prior conversation history in current session")

class DiscoveryIntent(BaseModel):
    objective: str = Field(..., description="Extracted user objective")
    category: str = Field(default="general", description="Category: shopping, education, books, developer, academic, tools, business, troubleshooting, general")
    main_topic: str = Field(..., description="Primary topic")
    related_topics: List[str] = Field(default_factory=list, description="Relevant subtopics or related fields")
    detected_language: str = Field(default="en", description="Detected language code or name, e.g. en, fr, ar, darija, de")
    missing_information: Optional[str] = Field(default=None, description="Key missing info if clarification is required")

class DiscoverySearchPlan(BaseModel):
    queries: List[str] = Field(..., min_length=1, description="Targeted queries for search engines (English/multilingual for high recall)")
    recommended_sources: List[str] = Field(..., min_length=1, description="List of source IDs (e.g. web_search, github, openalex, openlibrary)")
    resource_types: List[str] = Field(default_factory=list, description="Types of resources to look for (courses, tutorials, stores, papers, etc.)")
    reasoning: Optional[str] = Field(default=None, description="Explanation of why these sources and queries were selected")

class DiscoveryChatResponse(BaseModel):
    status: str = Field(..., description="'success', 'clarification', 'not_configured', or 'error'")
    configured: bool = Field(..., description="Whether AI API is configured")
    message: str = Field(..., description="AI response to the user in their language")
    understanding: Optional[str] = Field(default=None, description="Summary of what ELORA understood in user's language")
    needs_clarification: bool = Field(default=False, description="True if clarification is required before searching")
    clarification_question: Optional[str] = Field(default=None, description="Single clarification question if needed")
    intent: Optional[DiscoveryIntent] = Field(default=None)
    search_plan: Optional[DiscoverySearchPlan] = Field(default=None)
    error_detail: Optional[str] = Field(default=None)

class DiscoverySearchRequest(BaseModel):
    queries: List[str] = Field(..., min_length=1, description="Search queries to execute")
    sources: Optional[List[str]] = Field(default=None, description="Target source IDs. Defaults to enabled public connectors.")
    mode: Optional[str] = Field(default="general", description="Research mode: general, technical, problem_discovery")
    limit_per_source: Optional[int] = Field(default=10, ge=1, le=30)
    original_objective: Optional[str] = Field(default=None, description="Original user goal for ranking/explanation")
    language: Optional[str] = Field(default="en", description="Response language")

class DiscoverySearchResponse(BaseModel):
    job_id: str
    queries_executed: List[str]
    total_results: int
    results: List[ResearchResultResponse]
    grouped_by_type: Dict[str, List[ResearchResultResponse]] = {}
    summary: Optional[str] = None
    sources_queried: List[str] = []
