from datetime import datetime, timezone

def _utcnow():
    return datetime.now(timezone.utc)
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, JSON, Boolean, Index
from sqlalchemy.orm import relationship
from app.database.session import Base

class ResearchJob(Base):
    __tablename__ = "research_jobs"

    id = Column(String(36), primary_key=True, index=True)
    query = Column(String(500), nullable=False, index=True)
    mode = Column(String(50), default="general") # general, technical, problem_discovery
    status = Column(String(50), default="pending", index=True) # pending, running, completed, failed, cancelled
    progress = Column(Float, default=0.0) # 0.0 to 100.0
    selected_sources = Column(JSON, default=list) # e.g. ["hackernews", "web_search", "github"]
    filters = Column(JSON, default=dict)
    limit_per_source = Column(Integer, default=15)
    total_results_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=_utcnow, index=True)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    completed_at = Column(DateTime, nullable=True)

    results = relationship("ResearchResult", back_populates="job", cascade="all, delete-orphan")
    reports = relationship("ResearchReport", back_populates="job", cascade="all, delete-orphan")
    logs = relationship("CollectionLog", back_populates="job", cascade="all, delete-orphan")


class Source(Base):
    __tablename__ = "sources"

    id = Column(String(50), primary_key=True) # e.g., "hackernews", "duckduckgo", "github"
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), default="general")
    is_enabled = Column(Boolean, default=True)
    requires_auth = Column(Boolean, default=False)
    auth_status = Column(String(50), default="not_required") # not_required, configured, missing_key
    supported_content_types = Column(JSON, default=list)
    rate_limit_per_minute = Column(Integer, default=30)
    last_health_check = Column(DateTime, nullable=True)
    health_status = Column(String(50), default="operational") # operational, degraded, offline


class ResearchResult(Base):
    __tablename__ = "research_results"

    id = Column(String(64), primary_key=True, index=True) # composite or hash id
    job_id = Column(String(36), ForeignKey("research_jobs.id"), nullable=False, index=True)
    source_name = Column(String(50), nullable=False, index=True)
    source_item_id = Column(String(255), nullable=True)
    title = Column(String(500), nullable=False)
    content_snippet = Column(Text, nullable=True)
    source_url = Column(String(1000), nullable=False)
    author = Column(String(255), nullable=True)
    published_at = Column(DateTime, nullable=True)
    collected_at = Column(DateTime, default=_utcnow)
    content_type = Column(String(50), default="article") # discussion, issue, paper, article, doc
    engagement_metrics = Column(JSON, default=dict) # {"score": 10, "comments": 5, "stars": 20}
    metadata_fields = Column(JSON, default=dict) # raw source-specific fields
    relevance_score = Column(Float, default=0.0, index=True)
    is_duplicate = Column(Boolean, default=False)
    duplicate_of = Column(String(64), nullable=True)

    job = relationship("ResearchJob", back_populates="results")

    __table_args__ = (
        Index("ix_research_results_job_dup_rel", "job_id", "is_duplicate", "relevance_score"),
    )


class ResearchReport(Base):
    __tablename__ = "research_reports"

    id = Column(String(36), primary_key=True, index=True)
    job_id = Column(String(36), ForeignKey("research_jobs.id"), nullable=False, unique=True)
    executive_summary = Column(Text, nullable=False)
    main_findings = Column(JSON, default=list) # list of {theme, description, evidence_ids}
    recurring_problems = Column(JSON, default=list) # list of {problem, frequency, evidence_ids}
    perspectives = Column(JSON, default=list) # conflicting viewpoints
    existing_solutions = Column(JSON, default=list)
    potential_opportunities = Column(JSON, default=list)
    limitations = Column(JSON, default=list)
    collection_stats = Column(JSON, default=dict)
    created_at = Column(DateTime, default=_utcnow)

    job = relationship("ResearchJob", back_populates="reports")


class CollectionLog(Base):
    __tablename__ = "collection_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(36), ForeignKey("research_jobs.id"), nullable=False, index=True)
    source_name = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False) # success, error, warning
    message = Column(Text, nullable=False)
    items_collected = Column(Integer, default=0)
    duration_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=_utcnow)

    job = relationship("ResearchJob", back_populates="logs")


class ResultFeedback(Base):
    __tablename__ = "result_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(36), ForeignKey("research_jobs.id"), nullable=False, index=True)
    result_id = Column(String(64), ForeignKey("research_results.id"), nullable=False, index=True)
    feedback_type = Column(String(50), nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


class WishlistItem(Base):
    __tablename__ = "wishlist_items"

    id = Column(String(64), primary_key=True, index=True)
    result_id = Column(String(64), nullable=True, index=True)
    job_id = Column(String(36), nullable=True)
    source_name = Column(String(50), nullable=False, index=True)
    source_item_id = Column(String(255), nullable=True)
    title = Column(String(500), nullable=False)
    content_snippet = Column(Text, nullable=True)
    source_url = Column(String(1000), nullable=False)
    canonical_url = Column(String(1000), nullable=False, unique=True, index=True)
    author = Column(String(255), nullable=True)
    content_type = Column(String(50), default="article", index=True)
    published_at = Column(DateTime, nullable=True)
    saved_relevance_score = Column(Float, default=0.0)
    validation_status = Column(String(50), default="UNCHECKED")
    metadata_fields = Column(JSON, default=dict)
    saved_at = Column(DateTime, default=_utcnow, index=True)


class NewsFeed(Base):
    __tablename__ = "news_feeds"

    id = Column(String(64), primary_key=True)  # e.g. "bbc_world", "aljazeera_all", "dw_en", "france24_en"
    publisher = Column(String(100), nullable=False, index=True)  # e.g. "BBC News"
    name = Column(String(150), nullable=False)  # e.g. "BBC News - World"
    feed_url = Column(String(500), nullable=False, unique=True)
    category = Column(String(50), default="world", index=True)  # world, technology, business, politics, investigations, science
    language = Column(String(10), default="en", index=True)  # en, fr, ar
    is_enabled = Column(Boolean, default=True)

    # Ingestion & Health Tracking
    etag = Column(String(255), nullable=True)
    last_modified_header = Column(String(255), nullable=True)
    last_attempted_at = Column(DateTime, nullable=True)
    last_successful_at = Column(DateTime, nullable=True)
    http_status = Column(Integer, nullable=True)
    response_time_ms = Column(Integer, default=0)
    articles_count = Column(Integer, default=0)
    latest_pub_date = Column(DateTime, nullable=True)
    health_status = Column(String(50), default="operational")  # operational, temporarily_unavailable, invalid_feed, access_restricted, disabled
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    articles = relationship("IndexedNewsArticle", back_populates="feed", cascade="all, delete-orphan")


class IndexedNewsArticle(Base):
    __tablename__ = "indexed_news_articles"

    id = Column(String(64), primary_key=True, index=True)  # SHA-256 hash of canonical_url
    feed_id = Column(String(64), ForeignKey("news_feeds.id"), nullable=False, index=True)
    publisher = Column(String(100), nullable=False, index=True)
    title = Column(String(500), nullable=False, index=True)
    content_snippet = Column(Text, nullable=True)
    source_url = Column(String(1000), nullable=False)
    canonical_url = Column(String(1000), nullable=False, unique=True, index=True)
    author = Column(String(255), nullable=True)
    published_at = Column(DateTime, nullable=True, index=True)
    language = Column(String(10), default="en", index=True)
    category = Column(String(50), default="world", index=True)
    tags = Column(JSON, default=list)
    image_url = Column(String(1000), nullable=True)
    guid = Column(String(500), nullable=True)
    retrieved_at = Column(DateTime, default=_utcnow, index=True)
    metadata_fields = Column(JSON, default=dict)

    feed = relationship("NewsFeed", back_populates="articles")

    __table_args__ = (
        Index("ix_news_articles_pub_date", "published_at"),
        Index("ix_news_articles_publisher_cat", "publisher", "category"),
    )
