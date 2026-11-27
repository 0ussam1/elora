import re
import hashlib
import email.utils
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
from urllib.parse import urlparse, urlunparse
from app.connectors.base import RawResult
from app.models.database import ResearchResult
from app.pipeline.query_analyzer import detect_language


# Transparent source quality & category classification (never fabricates factual correctness)
SOURCE_QUALITY_META: Dict[str, Dict[str, Any]] = {
    "arxiv": {"source_quality_tier": "academic_preprint", "source_quality_label": "Academic Repository (Preprint)", "is_academic": True},
    "openalex": {"source_quality_tier": "peer_reviewed_index", "source_quality_label": "Academic Research Index", "is_academic": True},
    "crossref": {"source_quality_tier": "peer_reviewed_index", "source_quality_label": "DOI Scholarly Metadata", "is_academic": True},
    "semantic_scholar": {"source_quality_tier": "peer_reviewed_index", "source_quality_label": "Academic Literature Graph", "is_academic": True},
    "core": {"source_quality_tier": "open_access_academic", "source_quality_label": "Open-Access Research Repository", "is_academic": True},
    "zenodo": {"source_quality_tier": "research_repository", "source_quality_label": "Research Data & Artifact Repository", "is_academic": True},
    "cia_reading_room": {"source_quality_tier": "government_archive", "source_quality_label": "Government FOIA Archive", "is_academic": False},
    "fbi_vault": {"source_quality_tier": "government_archive", "source_quality_label": "Government FOIA Archive", "is_academic": False},
    "nsa_archive": {"source_quality_tier": "government_archive", "source_quality_label": "Government Declassification Archive", "is_academic": False},
    "nara": {"source_quality_tier": "government_archive", "source_quality_label": "National Government Archive", "is_academic": False},
    "nat_sec_archive": {"source_quality_tier": "investigative_archive", "source_quality_label": "Institutional Investigative Archive", "is_academic": True},
    "icij_offshore": {"source_quality_tier": "investigative_journalism", "source_quality_label": "Investigative Journalism Database", "is_academic": False},
    "wikipedia": {"source_quality_tier": "encyclopedic_reference", "source_quality_label": "Collaborative Encyclopedia", "is_academic": False},
    "internet_archive": {"source_quality_tier": "digital_archive", "source_quality_label": "Digital Historical Archive", "is_academic": False},
    "openlibrary": {"source_quality_tier": "book_catalog", "source_quality_label": "Open Book Catalog", "is_academic": False},
    "github": {"source_quality_tier": "technical_repository", "source_quality_label": "Code & Technical Documentation", "is_academic": False},
    "stackexchange": {"source_quality_tier": "technical_qa", "source_quality_label": "Technical Q&A Community", "is_academic": False},
    "kaggle": {"source_quality_tier": "dataset_repository", "source_quality_label": "Data Science & Datasets", "is_academic": False},
    "hackernews": {"source_quality_tier": "community_discussion", "source_quality_label": "Tech Community Discussion", "is_academic": False},
    "reddit": {"source_quality_tier": "community_discussion", "source_quality_label": "Community Forum Discussion", "is_academic": False},
    "discourse": {"source_quality_tier": "community_discussion", "source_quality_label": "Public Forum Discussion", "is_academic": False},
    "lemmy": {"source_quality_tier": "community_discussion", "source_quality_label": "Federated Community Discussion", "is_academic": False},
    "mastodon": {"source_quality_tier": "social_microblog", "source_quality_label": "Federated Public Posts", "is_academic": False},
    "web_search": {"source_quality_tier": "web_index", "source_quality_label": "General Web Index", "is_academic": False},
    # Dedicated News Sources
    "news": {"source_quality_tier": "international_news", "source_quality_label": "International News Wire", "is_academic": False},
    "bbc_news": {"source_quality_tier": "international_news", "source_quality_label": "BBC News International", "is_academic": False},
    "al_jazeera": {"source_quality_tier": "international_news", "source_quality_label": "Al Jazeera Media Network", "is_academic": False},
    "deutsche_welle": {"source_quality_tier": "international_news", "source_quality_label": "Deutsche Welle (DW)", "is_academic": False},
    "france24": {"source_quality_tier": "international_news", "source_quality_label": "France 24 International", "is_academic": False},
    "the_guardian": {"source_quality_tier": "international_news", "source_quality_label": "The Guardian", "is_academic": False},
    "euronews": {"source_quality_tier": "international_news", "source_quality_label": "Euronews Network", "is_academic": False},
    "sky_news": {"source_quality_tier": "international_news", "source_quality_label": "Sky News", "is_academic": False},
    "propublica": {"source_quality_tier": "investigative_journalism", "source_quality_label": "ProPublica Investigative", "is_academic": False},
}


class Normalizer:
    @staticmethod
    def clean_text(text: str | None) -> str:
        if not text:
            return ""
        # Remove consecutive whitespaces, control chars, trim
        cleaned = re.sub(r'[\r\n\t]+', ' ', text)
        cleaned = re.sub(r'\s{2,}', ' ', cleaned)
        return cleaned.strip()

    @staticmethod
    def canonical_url(url: str) -> str:
        try:
            parsed = urlparse(url)
            # Remove tracking params like utm_*, ref, at_medium, etc.
            tracking_prefixes = ("utm_", "ref=", "at_medium", "at_campaign", "at_source", "feedname=", "feedtype=")
            filtered_query = "&".join(
                q for q in parsed.query.split("&")
                if q and not any(q.lower().startswith(p) for p in tracking_prefixes)
            )
            clean = parsed._replace(query=filtered_query, fragment="")
            return urlunparse(clean).rstrip("/")
        except Exception:
            return url

    @staticmethod
    def normalize_datetime(dt: Any) -> Optional[datetime]:
        """
        Normalize publication date into consistent UTC representation.
        Supports ISO-8601, RFC-822/2822 RSS formats, and standard date strings.
        Detects invalid/corrupted dates and never fabricates missing dates.
        """
        if dt is None:
            return None
        parsed_dt: Optional[datetime] = None
        if isinstance(dt, datetime):
            parsed_dt = dt
        elif isinstance(dt, str):
            raw = dt.strip()
            if not raw:
                return None
            # 1. Try ISO-8601
            try:
                parsed_dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except Exception:
                pass

            # 2. Try RFC-2822 / RFC-822 (standard RSS pubDate: e.g. "Fri, 27 Nov 2026 17:17:11 GMT")
            if parsed_dt is None:
                try:
                    parsed_dt = email.utils.parsedate_to_datetime(raw)
                except Exception:
                    pass

            # 3. Fallback to common date formats
            if parsed_dt is None:
                for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d %b %Y", "%B %d, %Y", "%Y"):
                    try:
                        parsed_dt = datetime.strptime(raw[:20], fmt)
                        break
                    except Exception:
                        continue
        if parsed_dt is None:
            return None

        if parsed_dt.tzinfo is None:
            parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
        else:
            parsed_dt = parsed_dt.astimezone(timezone.utc)

        now_utc = datetime.now(timezone.utc)
        # Reject impossible dates (before 1800 or > 2 days in future)
        if parsed_dt.year < 1800 or parsed_dt > (now_utc + timedelta(days=2)):
            return None

        return parsed_dt

    @classmethod
    def normalize(cls, raw: RawResult, job_id: str) -> ResearchResult:
        clean_title = cls.clean_text(raw.title)
        clean_snippet = cls.clean_text(raw.content_snippet)
        canon_url = cls.canonical_url(raw.source_url)
        norm_pub_at = cls.normalize_datetime(raw.published_at)

        # Unique deterministic ID based on canonical URL or source+itemId
        hash_input = f"{raw.source_name}:{raw.source_item_id or canon_url}"
        item_id = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()[:24]

        meta = dict(raw.metadata or {})
        lang = meta.get("language") or detect_language(f"{clean_title} {clean_snippet}")
        quality_info = SOURCE_QUALITY_META.get(raw.source_name, {
            "source_quality_tier": "general",
            "source_quality_label": "External Source",
            "is_academic": False,
        })
        meta["language"] = lang
        meta["date_status"] = "verified_date" if norm_pub_at else "missing_date"
        meta["source_quality_tier"] = quality_info["source_quality_tier"]
        meta["source_quality_label"] = quality_info["source_quality_label"]
        meta["is_academic"] = quality_info["is_academic"]
        if "is_open_access" not in meta:
            meta["is_open_access"] = raw.source_name in ("arxiv", "core", "zenodo", "wikipedia", "openalex", "internet_archive", "openlibrary")
        if "content_availability" not in meta:
            meta["content_availability"] = "snippet" if clean_snippet else "metadata_only"

        return ResearchResult(
            id=f"{job_id}_{item_id}",
            job_id=job_id,
            source_name=raw.source_name,
            source_item_id=raw.source_item_id,
            title=clean_title,
            content_snippet=clean_snippet,
            source_url=canon_url,
            author=cls.clean_text(raw.author) if raw.author else None,
            published_at=norm_pub_at,
            content_type=raw.content_type,
            engagement_metrics=raw.engagement_metrics or {},
            metadata_fields=meta,
            relevance_score=0.0,
            is_duplicate=False
        )
