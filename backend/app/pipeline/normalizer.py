import re
import hashlib
from typing import List, Dict, Any, Tuple
from urllib.parse import urlparse, urlunparse
from app.connectors.base import RawResult
from app.models.database import ResearchResult

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
            # Remove tracking params like utm_*, ref, etc.
            filtered_query = "&".join(
                q for q in parsed.query.split("&")
                if not q.startswith("utm_") and not q.startswith("ref=")
            )
            clean = parsed._replace(query=filtered_query, fragment="")
            return urlunparse(clean).rstrip("/")
        except Exception:
            return url

    @classmethod
    def normalize(cls, raw: RawResult, job_id: str) -> ResearchResult:
        clean_title = cls.clean_text(raw.title)
        clean_snippet = cls.clean_text(raw.content_snippet)
        canon_url = cls.canonical_url(raw.source_url)
        
        # Unique deterministic ID based on canonical URL or source+itemId
        hash_input = f"{raw.source_name}:{raw.source_item_id or canon_url}"
        item_id = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()[:24]

        return ResearchResult(
            id=f"{job_id}_{item_id}",
            job_id=job_id,
            source_name=raw.source_name,
            source_item_id=raw.source_item_id,
            title=clean_title,
            content_snippet=clean_snippet,
            source_url=canon_url,
            author=cls.clean_text(raw.author) if raw.author else None,
            published_at=raw.published_at,
            content_type=raw.content_type,
            engagement_metrics=raw.engagement_metrics or {},
            metadata_fields=raw.metadata or {},
            relevance_score=0.0,
            is_duplicate=False
        )
