"""
Hybrid Context-Aware Relevance Engine & Chronological Sorter for ELORA.

Combines:
  1. BM25 + Multilingual TF-IDF lexical & semantic similarity
  2. Exact Entity & Version matching with negative mismatch penalties (e.g. GTA 6 vs GTA 5)
  3. Cross-lingual concept matching (EN <-> FR <-> AR)
  4. Metadata & intent-aware weighting
  5. Evidence passage extraction & transparent match explanations
  6. Gentle secondary source diversity balancing
  7. Deterministic chronological sorting (Newest First default, Most Relevant, Oldest First)
"""
import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.models.database import ResearchResult
from app.pipeline.query_analyzer import QueryAnalysis, QueryAnalyzer, tokenize_multilingual

MIN_RELEVANCE_THRESHOLD = 0.15

# Roman numeral equivalents for common game/product versions
_ROMAN_TO_ARABIC = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8"}
_ARABIC_TO_ROMAN = {v: k for k, v in _ROMAN_TO_ARABIC.items()}

_INTENT_SOURCE_BOOSTS: Dict[str, Set[str]] = {
    "academic": {"arxiv", "openalex", "crossref", "semantic_scholar", "core", "zenodo"},
    "technical": {"github", "stackexchange", "arxiv", "discourse", "kaggle"},
    "tutorial": {"github", "stackexchange", "wikipedia", "web_search"},
    "discussion": {"hackernews", "reddit", "discourse", "lemmy", "mastodon"},
    "historical": {"cia_reading_room", "fbi_vault", "nsa_archive", "nat_sec_archive", "nara", "icij_offshore", "internet_archive"},
    "books_datasets": {"openlibrary", "zenodo", "kaggle", "internet_archive"},
    "news": {"hackernews", "reddit", "mastodon", "lemmy", "web_search"},
}


class Ranker:
    @staticmethod
    def _extract_tokens(text: str) -> List[str]:
        return tokenize_multilingual(text, keep_short_versions=True)

    @staticmethod
    def _bm25_scores(query_tokens: List[str], docs_tokens: List[List[str]], k1: float = 1.5, b: float = 0.75) -> List[float]:
        """Lightweight BM25 lexical scoring normalized to [0, 1]."""
        n_docs = len(docs_tokens)
        if n_docs == 0 or not query_tokens:
            return [0.0] * n_docs

        avg_dl = sum(len(d) for d in docs_tokens) / max(n_docs, 1)
        avg_dl = max(avg_dl, 1.0)

        # Document frequency for query terms
        df: Dict[str, int] = {}
        unique_q = set(query_tokens)
        for doc in docs_tokens:
            doc_set = set(doc)
            for qt in unique_q:
                if qt in doc_set:
                    df[qt] = df.get(qt, 0) + 1

        raw_scores: List[float] = []
        for doc in docs_tokens:
            dl = len(doc)
            tf_map: Dict[str, int] = {}
            for tok in doc:
                tf_map[tok] = tf_map.get(tok, 0) + 1

            score = 0.0
            for qt in unique_q:
                tf = tf_map.get(qt, 0)
                if tf == 0:
                    continue
                n_q = df.get(qt, 0)
                idf = math.log(1.0 + (n_docs - n_q + 0.5) / (n_q + 0.5))
                denom = tf + k1 * (1.0 - b + b * (dl / avg_dl))
                score += idf * ((tf * (k1 + 1.0)) / max(denom, 1e-6))
            raw_scores.append(score)

        max_s = max(raw_scores) if raw_scores else 0.0
        if max_s <= 0:
            return [0.0] * n_docs
        return [s / max_s for s in raw_scores]

    @staticmethod
    def _check_entity_version_signals(
        analysis: QueryAnalysis, text_lower: str, title_lower: str
    ) -> Tuple[float, float, List[str], List[str]]:
        """
        Evaluate exact entity/version match and negative version mismatch signals.
        Returns: (boost, penalty_multiplier, matched_entities, reasons)
        """
        if not analysis.entities:
            return 0.0, 1.0, [], []

        boost = 0.0
        penalty_mult = 1.0
        matched_entities: List[str] = []
        reasons: List[str] = []

        for ev in analysis.entities:
            ent = ev.entity
            ver = ev.version
            roman_ver = _ARABIC_TO_ROMAN.get(ver)

            # Check if entity appears in text
            ent_present = bool(re.search(rf"\b{re.escape(ent)}\b", text_lower))
            if not ent_present:
                continue

            # Check for exact target version paired with entity (e.g. "gta 6", "gta vi", "python 3.13", "gpt-6")
            ver_patterns = [re.escape(ver)]
            if roman_ver:
                ver_patterns.append(re.escape(roman_ver))
            ver_regex = "|".join(ver_patterns)

            exact_phrase_match = bool(
                re.search(rf"\b{re.escape(ent)}[\s\-_]*(?:{ver_regex})\b", text_lower)
            )
            title_exact_match = bool(
                re.search(rf"\b{re.escape(ent)}[\s\-_]*(?:{ver_regex})\b", title_lower)
            )

            if exact_phrase_match:
                matched_entities.append(ev.full_phrase)
                boost += 0.35 if title_exact_match else 0.25
                reasons.append(f"Exact entity & version match: {ev.full_phrase}")
            else:
                # Check if document mentions the SAME entity with a DIFFERENT version!
                other_versions = re.findall(
                    rf"\b{re.escape(ent)}[\s\-_]*(v?\d+(?:\.\d+){{0,2}}|ii|iii|iv|v|vi|vii|viii)\b",
                    text_lower,
                )
                other_clean = {
                    _ROMAN_TO_ARABIC.get(v.lstrip("v"), v.lstrip("v"))
                    for v in other_versions
                } - {ver}

                if other_clean and not analysis.is_comparison:
                    # Strong penalty: document is about a different version (e.g. GTA 5 when user asked GTA 6)
                    penalty_mult = min(penalty_mult, 0.25)
                    reasons.append(
                        f"Version mismatch penalty: mentions {ent} {', '.join(sorted(other_clean))} instead of {ev.full_phrase}"
                    )

        if analysis.is_comparison and len(matched_entities) >= 2:
            boost += 0.15
            reasons.append("Comparison match across requested versions")

        return boost, penalty_mult, matched_entities, reasons

    @staticmethod
    def _extract_best_passage(query_tokens: Set[str], title: str, snippet: str) -> str:
        """Select the most relevant sentence/passage as traceable evidence."""
        if not snippet:
            return title or ""
        sentences = re.split(r"(?<=[.!?])\s+", snippet.strip())
        if len(sentences) <= 1:
            return snippet[:280]
        best_sent = sentences[0]
        best_hits = -1
        for sent in sentences:
            s_tokens = set(tokenize_multilingual(sent))
            hits = len(query_tokens & s_tokens)
            if hits > best_hits:
                best_hits = hits
                best_sent = sent
        return best_sent[:280]

    @classmethod
    def rank(
        cls,
        query: str,
        items: List[ResearchResult],
        mode: str = "general",
        analysis: Optional[QueryAnalysis] = None,
    ) -> List[ResearchResult]:
        if not items:
            return items

        qa = analysis or QueryAnalyzer.analyze(query)
        expanded_query = " ".join([qa.normalized_query] + qa.multilingual_expansions).strip()

        # Build multilingual corpus: Title + Snippet + Metadata Tags/Topics
        doc_texts: List[str] = []
        docs_tokens: List[List[str]] = []
        for item in items:
            meta = item.metadata_fields or {}
            tags = meta.get("tags") or meta.get("categories") or meta.get("topics") or []
            tag_str = " ".join(str(t) for t in tags) if isinstance(tags, list) else str(tags)
            full_text = f"{item.title} {item.content_snippet or ''} {tag_str}".strip()
            doc_texts.append(full_text)
            docs_tokens.append(cls._extract_tokens(full_text))

        # 1. TF-IDF Cosine Similarity (multilingual token analyzer)
        try:
            vectorizer = TfidfVectorizer(
                tokenizer=cls._extract_tokens,
                token_pattern=None,
                lowercase=True,
                max_features=2000,
            )
            tfidf_matrix = vectorizer.fit_transform([expanded_query] + doc_texts)
            sims = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])[0]
        except Exception:
            sims = np.zeros(len(items))

        # 2. BM25 Lexical Scores
        q_tokens_list = cls._extract_tokens(expanded_query)
        q_tokens_set = set(q_tokens_list)
        bm25_list = cls._bm25_scores(q_tokens_list, docs_tokens)

        now_utc = datetime.now(timezone.utc)

        for idx, item in enumerate(items):
            tfidf_score = float(sims[idx]) if idx < len(sims) else 0.0
            bm25_score = bm25_list[idx] if idx < len(bm25_list) else 0.0

            title_lower = (item.title or "").lower()
            snippet_lower = (item.content_snippet or "").lower()
            full_lower = f"{title_lower} {snippet_lower}"

            # 3. Title & Context Keyword Overlap
            title_tokens = set(cls._extract_tokens(item.title or ""))
            doc_tokens_set = set(docs_tokens[idx])
            orig_q_tokens = set(qa.keywords) if qa.keywords else q_tokens_set

            title_overlap = len(orig_q_tokens & title_tokens) / max(len(orig_q_tokens), 1)
            context_overlap = len(q_tokens_set & doc_tokens_set) / max(len(q_tokens_set), 1)

            # 4. Exact Entity & Version Signals
            ev_boost, ev_penalty, matched_entities, ev_reasons = cls._check_entity_version_signals(
                qa, full_lower, title_lower
            )

            # 5. Cross-lingual concept bonus
            cross_lingual_match = False
            if qa.multilingual_expansions:
                for exp in qa.multilingual_expansions:
                    if exp.lower() in full_lower:
                        cross_lingual_match = True
                        break

            # 6. Recency signal (secondary, stronger for 'news' intent)
            recency_bonus = 0.0
            if item.published_at is not None:
                pub = item.published_at
                if pub.tzinfo is None:
                    pub = pub.replace(tzinfo=timezone.utc)
                age_days = max((now_utc - pub).total_seconds() / 86400.0, 0.0)
                if age_days <= 30:
                    recency_bonus = 0.10 if qa.time_preference == "recent" else 0.04
                elif age_days <= 180:
                    recency_bonus = 0.06 if qa.time_preference == "recent" else 0.02
                elif age_days <= 365:
                    recency_bonus = 0.02

            # 7. Engagement / Authority bonus (small, never overrides entity accuracy)
            engagement_bonus = 0.0
            if item.engagement_metrics:
                pts = item.engagement_metrics.get("points") or item.engagement_metrics.get("score") or 0
                comments = item.engagement_metrics.get("comments_count") or item.engagement_metrics.get("comments") or 0
                views = item.engagement_metrics.get("view_count") or 0
                citations = item.engagement_metrics.get("citations") or 0
                raw_eng = pts + (comments * 2) + (views * 0.01) + (citations * 3)
                if raw_eng > 0:
                    engagement_bonus = min(math.log10(raw_eng + 1) * 0.05, 0.12)

            # 8. Mode & Intent-aware weighting
            mode_multiplier = 1.0
            if mode == "problem_discovery":
                problem_kws = {"bug", "issue", "problem", "fail", "error", "broken", "limitation", "complaint", "struggle", "fix"}
                p_hits = sum(1 for kw in problem_kws if kw in full_lower)
                if p_hits > 0:
                    mode_multiplier = 1.0 + min(p_hits * 0.08, 0.32)
            elif mode == "technical":
                if item.source_name in _INTENT_SOURCE_BOOSTS["technical"]:
                    mode_multiplier = 1.15

            if qa.intent in _INTENT_SOURCE_BOOSTS and item.source_name in _INTENT_SOURCE_BOOSTS[qa.intent]:
                mode_multiplier *= 1.08

            # Combine hybrid signals
            base_score = (
                (bm25_score * 0.30)
                + (tfidf_score * 0.25)
                + (title_overlap * 0.25)
                + (context_overlap * 0.15)
                + (0.15 if cross_lingual_match else 0.0)
                + ev_boost
                + recency_bonus
                + engagement_bonus
            )

            # Apply negative penalty if entity version mismatched (e.g. GTA 5 for GTA 6 query)
            final_score = round(min(max(base_score * mode_multiplier * ev_penalty, 0.0), 1.0), 3)
            item.relevance_score = final_score

            # Classify relevance tier & build transparent match explanation
            if ev_penalty < 1.0 or final_score < MIN_RELEVANCE_THRESHOLD:
                match_tier = "irrelevant" if final_score < MIN_RELEVANCE_THRESHOLD else "weakly_related"
            elif ev_boost >= 0.25 and title_overlap >= 0.5:
                match_tier = "exact_match"
            elif final_score >= 0.55:
                match_tier = "strong_contextual"
            elif final_score >= 0.30:
                match_tier = "related_subject"
            else:
                match_tier = "weakly_related"

            reasons = list(ev_reasons)
            if title_overlap >= 0.5:
                reasons.append(f"High title keyword match ({int(title_overlap * 100)}%)")
            if cross_lingual_match:
                reasons.append("Cross-lingual concept match")
            if qa.intent != "general" and item.source_name in _INTENT_SOURCE_BOOSTS.get(qa.intent, set()):
                reasons.append(f"Matches {qa.intent} intent source")
            if not reasons and final_score >= MIN_RELEVANCE_THRESHOLD:
                reasons.append("Contextual lexical/semantic match")

            meta = dict(item.metadata_fields or {})
            meta["match_tier"] = match_tier
            meta["is_relevant"] = final_score >= MIN_RELEVANCE_THRESHOLD
            meta["matched_entities"] = matched_entities
            meta["match_reasons"] = reasons[:4]
            meta["query_intent"] = qa.intent
            meta["evidence_excerpt"] = cls._extract_best_passage(q_tokens_set, item.title or "", item.content_snippet or "")
            item.metadata_fields = meta

        # Sort by relevance first before diversity pass
        items.sort(key=lambda x: x.relevance_score, reverse=True)

        # Gentle secondary source diversity: slightly penalize >3 items from the same provider
        # only in ranking order without dropping valid high-relevance results
        provider_counts: Dict[str, int] = {}
        for item in items:
            cnt = provider_counts.get(item.source_name, 0) + 1
            provider_counts[item.source_name] = cnt
            if cnt > 3 and item.relevance_score >= MIN_RELEVANCE_THRESHOLD:
                item.relevance_score = round(max(item.relevance_score - min((cnt - 3) * 0.02, 0.08), MIN_RELEVANCE_THRESHOLD), 3)

        items.sort(key=lambda x: x.relevance_score, reverse=True)
        return items

    @staticmethod
    def sort_results(items: List[ResearchResult], sort_by: str = "newest") -> List[ResearchResult]:
        """
        Deterministic sorting supporting:
          - 'newest' (default): Newest to oldest by UTC published_at; unknown dates AFTER dated records.
          - 'relevant': Highest relevance_score first, recency as tie-breaker.
          - 'oldest': Oldest to newest by UTC published_at; unknown dates AFTER dated records.
        """
        if not items:
            return items

        def _ts(item: ResearchResult) -> float:
            if item.published_at is None:
                return 0.0
            dt = item.published_at
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()

        if sort_by == "relevant":
            return sorted(items, key=lambda x: (-x.relevance_score, -_ts(x), x.id))
        elif sort_by == "oldest":
            dated = [x for x in items if x.published_at is not None]
            undated = [x for x in items if x.published_at is None]
            dated.sort(key=lambda x: (_ts(x), -x.relevance_score, x.id))
            undated.sort(key=lambda x: (-x.relevance_score, x.id))
            return dated + undated
        else:
            # Default: 'newest' — strictly newest to oldest, undated records AFTER dated records
            dated = [x for x in items if x.published_at is not None]
            undated = [x for x in items if x.published_at is None]
            dated.sort(key=lambda x: (-_ts(x), -x.relevance_score, x.id))
            undated.sort(key=lambda x: (-x.relevance_score, x.id))
            return dated + undated
