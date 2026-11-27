"""
Multi-Signal Duplicate Detection & Provider Reference Merging for ELORA.

Detects duplicates via:
  1. Normalized DOI (cross-source scholarly match: OpenAlex, Crossref, Semantic Scholar, CORE, arXiv)
  2. Canonical URL (scheme/www/trailing-slash normalized)
  3. Exact Unicode-safe normalized title (preserving Arabic, French, and version digits)
  4. High-confidence title + snippet Jaccard similarity (with strict version protection so
     distinct versions like "GTA 6" and "GTA 5" or "Python 3.13" and "Python 3.12" are NEVER merged)

When a duplicate is detected, provider references and richer metadata are merged into the
surviving primary record so no provenance is lost.
"""
import hashlib
import re
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from app.core.cache import fingerprint_cache
from app.models.database import ResearchResult
from app.pipeline.query_analyzer import tokenize_multilingual

_VERSION_NUM_RE = re.compile(r"\b\d+(?:\.\d+){0,2}\b")


class Deduplicator:
    @staticmethod
    def _simplify_title(title: str) -> str:
        """Unicode-aware title normalization preserving letters, Arabic, accents, and digits."""
        if not title:
            return ""
        cached = fingerprint_cache.get(f"t:{title}")
        if cached is not None:
            return cached
        cleaned = re.sub(r"[^\w\u0600-\u06FF\s]", " ", title.lower())
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        fingerprint_cache.set(f"t:{title}", cleaned)
        return cleaned

    @staticmethod
    def _normalize_url_key(url: str) -> str:
        try:
            p = urlparse((url or "").strip())
            host = p.netloc.lower().lstrip("www.")
            path = p.path.rstrip("/")
            return f"{host}{path}"
        except Exception:
            return (url or "").strip().lower()

    @staticmethod
    def _extract_doi(item: ResearchResult) -> Optional[str]:
        meta = item.metadata_fields or {}
        doi = meta.get("doi") or meta.get("DOI")
        if doi and isinstance(doi, str):
            doi_clean = doi.lower().replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
            if doi_clean.startswith("10."):
                return doi_clean
        if item.source_url and "doi.org/10." in item.source_url.lower():
            return item.source_url.lower().split("doi.org/", 1)[-1].strip("/")
        return None

    @staticmethod
    def _jaccard(a: Set[str], b: Set[str]) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    @classmethod
    def _merge_into_primary(cls, primary: ResearchResult, dup: ResearchResult) -> None:
        """Preserve all provider references & richer metadata on the surviving record."""
        p_meta = dict(primary.metadata_fields or {})
        also = list(p_meta.get("also_found_in", []))
        also.append({
            "source_name": dup.source_name,
            "source_url": dup.source_url,
            "source_item_id": dup.source_item_id,
        })
        p_meta["also_found_in"] = also

        # Preserve DOI if primary lacks it
        dup_doi = cls._extract_doi(dup)
        if dup_doi and not p_meta.get("doi"):
            p_meta["doi"] = dup_doi

        # Preserve richer snippet if primary is shorter
        if dup.content_snippet and len(dup.content_snippet) > len(primary.content_snippet or "") + 30:
            primary.content_snippet = dup.content_snippet

        # Preserve valid publication date if primary lacks one
        if primary.published_at is None and dup.published_at is not None:
            primary.published_at = dup.published_at
            p_meta["date_status"] = "verified_date"

        primary.metadata_fields = p_meta

    @classmethod
    def deduplicate(cls, items: List[ResearchResult]) -> List[ResearchResult]:
        seen_dois: Dict[str, ResearchResult] = {}
        seen_urls: Dict[str, ResearchResult] = {}
        seen_titles: Dict[str, ResearchResult] = {}
        kept_signatures: List[Tuple[ResearchResult, Set[str], Set[str], Set[str]]] = []

        for item in items:
            item.is_duplicate = False
            item.duplicate_of = None

            # 1. Exact DOI match (academic cross-source deduplication)
            doi = cls._extract_doi(item)
            if doi:
                if doi in seen_dois:
                    primary = seen_dois[doi]
                    item.is_duplicate = True
                    item.duplicate_of = primary.id
                    cls._merge_into_primary(primary, item)
                    continue
                seen_dois[doi] = item

            # 2. Canonical URL match
            url_key = cls._normalize_url_key(item.source_url)
            if url_key:
                if url_key in seen_urls:
                    primary = seen_urls[url_key]
                    item.is_duplicate = True
                    item.duplicate_of = primary.id
                    cls._merge_into_primary(primary, item)
                    continue
                seen_urls[url_key] = item

            # 3. Exact Unicode-safe normalized title match
            simplified = cls._simplify_title(item.title)
            if len(simplified) > 10:
                if simplified in seen_titles:
                    primary = seen_titles[simplified]
                    item.is_duplicate = True
                    item.duplicate_of = primary.id
                    cls._merge_into_primary(primary, item)
                    continue
                seen_titles[simplified] = item

            # 4. Near-duplicate check via title + snippet overlap (with strict version guard)
            title_tokens = set(tokenize_multilingual(item.title or ""))
            snippet_tokens = set(tokenize_multilingual(item.content_snippet or ""))
            version_nums = set(_VERSION_NUM_RE.findall(item.title or ""))

            matched_primary: Optional[ResearchResult] = None
            if len(title_tokens) >= 4:
                for cand_primary, cand_t_tok, cand_s_tok, cand_vers in kept_signatures:
                    # Never merge if explicit version numbers in titles differ (e.g. GTA 6 vs GTA 5)
                    if version_nums and cand_vers and version_nums != cand_vers:
                        continue
                    t_sim = cls._jaccard(title_tokens, cand_t_tok)
                    if t_sim >= 0.85:
                        if not snippet_tokens or not cand_s_tok or cls._jaccard(snippet_tokens, cand_s_tok) >= 0.50:
                            matched_primary = cand_primary
                            break

            if matched_primary is not None:
                item.is_duplicate = True
                item.duplicate_of = matched_primary.id
                cls._merge_into_primary(matched_primary, item)
                continue

            kept_signatures.append((item, title_tokens, snippet_tokens, version_nums))

        return items
