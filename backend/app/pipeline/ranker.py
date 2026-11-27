"""
Calibrated Hybrid Relevance Engine & Match-Based Sorter for ELORA.

Evaluates multi-dimensional relevance (NOT title-only):
  1. Title relevance (exact phrase, entity/version, weighted token overlap)
  2. Description & full-content relevance (handles missing metadata gracefully)
  3. Topic, category & query qualifier relevance (e.g., "release date", "memory management")
  4. Calibrated semantic + lexical similarity (BM25 + multilingual TF-IDF)
  5. Exact Entity & Version matching with strict mismatch penalties (GTA 6 vs GTA 5)
  6. Cross-lingual concept matching (EN <-> FR <-> AR)
  7. Explainable match_reasons & match_breakdown (relevance != factual credibility)
  8. Default sorting: Highest Match -> Lowest Match ('relevant'), plus 'newest' and 'oldest'
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

MIN_RELEVANCE_THRESHOLD = 0.25

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

        avg_dl = max(sum(len(d) for d in docs_tokens) / max(n_docs, 1), 1.0)

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
    def _calibrate_cosine(raw_cos: float) -> float:
        """
        Calibrate raw TF-IDF cosine similarity (typically 0.05..0.65 for real docs)
        into a smooth [0.0, 1.0] semantic relevance signal.
        """
        if raw_cos <= 0.01:
            return 0.0
        # Smooth saturation: 0.15 -> ~0.46, 0.30 -> ~0.73, 0.50 -> ~0.91
        return min(1.0 - math.exp(-4.5 * raw_cos), 1.0)

    @staticmethod
    def _check_entity_version_signals(
        analysis: QueryAnalysis, text_lower: str, title_lower: str, desc_lower: str
    ) -> Tuple[float, float, List[str], List[str], bool]:
        """
        Evaluate exact entity/version match and negative version mismatch signals.
        Returns: (entity_score_0_to_1, penalty_multiplier, matched_entities, reasons, has_mismatch)
        """
        if not analysis.entities:
            return 0.0, 1.0, [], [], False

        matched_entities: List[str] = []
        reasons: List[str] = []
        total_ev_score = 0.0
        penalty_mult = 1.0
        has_mismatch = False

        for ev in analysis.entities:
            ent = ev.entity
            ver = ev.version
            roman_ver = _ARABIC_TO_ROMAN.get(ver)

            ent_present = bool(re.search(rf"\b{re.escape(ent)}\b", text_lower))
            if not ent_present:
                continue

            ver_patterns = [re.escape(ver)]
            if roman_ver:
                ver_patterns.append(re.escape(roman_ver))
            ver_regex = "|".join(ver_patterns)

            title_exact = bool(re.search(rf"\b{re.escape(ent)}[\s\-_]*(?:{ver_regex})\b", title_lower))
            desc_exact = bool(re.search(rf"\b{re.escape(ent)}[\s\-_]*(?:{ver_regex})\b", desc_lower))

            if title_exact or desc_exact:
                matched_entities.append(ev.full_phrase)
                if title_exact and desc_exact:
                    total_ev_score += 1.0
                    reasons.append(f"Exact entity & version match in title and description: {ev.full_phrase}")
                elif title_exact:
                    total_ev_score += 0.90
                    reasons.append(f"Exact entity & version match in title: {ev.full_phrase}")
                else:
                    total_ev_score += 0.80
                    reasons.append(f"Exact entity & version match in description: {ev.full_phrase}")
            else:
                other_versions = re.findall(
                    rf"\b{re.escape(ent)}[\s\-_]*(v?\d+(?:\.\d+){{0,2}}|ii|iii|iv|v|vi|vii|viii)\b",
                    text_lower,
                )
                other_clean = {
                    _ROMAN_TO_ARABIC.get(v.lstrip("v"), v.lstrip("v"))
                    for v in other_versions
                } - {ver}

                if other_clean and not analysis.is_comparison:
                    has_mismatch = True
                    penalty_mult = min(penalty_mult, 0.22)
                    reasons.append(
                        f"Incorrect version detected: {ent} {', '.join(sorted(other_clean))} instead of {ev.full_phrase}"
                    )

        avg_ev_score = min(total_ev_score / max(len(analysis.entities), 1), 1.0)
        if analysis.is_comparison and len(matched_entities) >= 2:
            avg_ev_score = 1.0
            reasons.append("Comparison match across all requested versions")
        elif analysis.entities and not matched_entities and not has_mismatch:
            # Target entity not found at all (e.g. "Rockstar Games" for "GTA 6 release date")
            penalty_mult = min(penalty_mult, 0.55)
            reasons.append(f"Related topic, missing target entity: {analysis.entities[0].full_phrase}")

        return avg_ev_score, penalty_mult, matched_entities, reasons, has_mismatch

    @staticmethod
    def _extract_best_passage(query_tokens: Set[str], title: str, snippet: str) -> str:
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

        doc_texts: List[str] = []
        docs_tokens: List[List[str]] = []
        for item in items:
            meta = item.metadata_fields or {}
            tags = meta.get("tags") or meta.get("categories") or meta.get("topics") or []
            tag_str = " ".join(str(t) for t in tags) if isinstance(tags, list) else str(tags)
            full_text = f"{item.title} {item.content_snippet or ''} {tag_str}".strip()
            doc_texts.append(full_text)
            docs_tokens.append(cls._extract_tokens(full_text))

        # 1. Calibrated TF-IDF Semantic Similarity
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

        orig_q_tokens = set(qa.keywords) if qa.keywords else q_tokens_set
        phrase_clean = qa.normalized_query.lower()

        for idx, item in enumerate(items):
            raw_cos = float(sims[idx]) if idx < len(sims) else 0.0
            sem_score = cls._calibrate_cosine(raw_cos)
            bm25_score = bm25_list[idx] if idx < len(bm25_list) else 0.0

            title_lower = (item.title or "").lower()
            desc_text = item.content_snippet or ""
            desc_lower = desc_text.lower()
            meta = dict(item.metadata_fields or {})
            tags = meta.get("tags") or meta.get("categories") or meta.get("topics") or []
            tag_str = (" ".join(str(t) for t in tags) if isinstance(tags, list) else str(tags)).lower()
            full_lower = f"{title_lower} {desc_lower} {tag_str}".strip()

            # Dimension 1: Title Relevance [0, 1]
            title_tokens = set(cls._extract_tokens(item.title or ""))
            title_overlap = len(orig_q_tokens & title_tokens) / max(len(orig_q_tokens), 1)
            title_phrase_bonus = 0.15 if (len(phrase_clean) >= 4 and phrase_clean in title_lower) else 0.0
            title_score = min(title_overlap + title_phrase_bonus, 1.0)

            # Dimension 2: Description / Content Relevance [0, 1]
            # Distinguish unavailable metadata from checked-and-irrelevant content
            has_description = len(desc_lower.strip()) >= 15
            if has_description:
                desc_tokens = set(cls._extract_tokens(desc_text))
                desc_overlap = len(q_tokens_set & desc_tokens) / max(len(q_tokens_set), 1)
                desc_phrase_bonus = 0.15 if (len(phrase_clean) >= 4 and phrase_clean in desc_lower) else 0.0
                desc_score = min(desc_overlap + desc_phrase_bonus, 1.0)
            else:
                # Missing snippet: do not treat as irrelevant; estimate conservatively from title
                desc_score = title_score * 0.70

            # Dimension 3: Topic & Qualifier Relevance [0, 1]
            qualifier_hits = 0
            if qa.qualifiers:
                for qf in qa.qualifiers:
                    if qf in full_lower:
                        qualifier_hits += 1
                qualifier_ratio = qualifier_hits / len(qa.qualifiers)
            else:
                qualifier_ratio = 1.0  # No extra qualifier required

            tag_tokens = set(cls._extract_tokens(tag_str))
            tag_overlap = len(q_tokens_set & tag_tokens) / max(len(q_tokens_set), 1) if tag_tokens else 0.0
            topic_score = min((qualifier_ratio * 0.75) + (tag_overlap * 0.25) + (0.25 if not qa.qualifiers and title_overlap >= 0.5 else 0.0), 1.0)

            # Dimension 4: Blended Semantic + Lexical Score [0, 1]
            lexical_semantic_score = (sem_score * 0.50) + (bm25_score * 0.50)

            # Dimension 5: Entity & Version Accuracy + Mismatch Penalty
            ev_score, ev_penalty, matched_entities, ev_reasons, has_mismatch = cls._check_entity_version_signals(
                qa, full_lower, title_lower, desc_lower
            )

            # Cross-lingual concept match boost
            cross_lingual_match = False
            if qa.multilingual_expansions:
                for exp in qa.multilingual_expansions:
                    if exp.lower() in full_lower:
                        cross_lingual_match = True
                        break

            # Intent compatibility (small calibrated bonus, <= 0.05)
            intent_bonus = 0.0
            if qa.intent in _INTENT_SOURCE_BOOSTS and item.source_name in _INTENT_SOURCE_BOOSTS[qa.intent]:
                intent_bonus = 0.05
            if mode == "problem_discovery":
                problem_kws = {"bug", "issue", "problem", "fail", "error", "broken", "limitation", "complaint", "struggle", "fix"}
                if any(kw in full_lower for kw in problem_kws):
                    intent_bonus = max(intent_bonus, 0.06)

            # Calibrated Weighted Scoring Model:
            # - If query has explicit entities (e.g. GTA 6, Python 3.13), entity/version accuracy has 0.30 weight
            # - Otherwise weights distribute across title (0.30), description (0.30), semantic+BM25 (0.25), topic (0.15)
            if qa.entities:
                raw_score = (
                    (title_score * 0.22)
                    + (desc_score * 0.24)
                    + (ev_score * 0.30)
                    + (topic_score * 0.12)
                    + (lexical_semantic_score * 0.12)
                    + (0.12 if cross_lingual_match else 0.0)
                    + intent_bonus
                )
                # If query has qualifiers (e.g. "release date") and entity matched, reward full qualifier coverage
                if qa.qualifiers and matched_entities and qualifier_hits == 0:
                    raw_score *= 0.78  # General GTA 6 article for "GTA 6 release date" stays moderate-high (~65-75%) instead of 95%
            else:
                raw_score = (
                    (title_score * 0.30)
                    + (desc_score * 0.28)
                    + (lexical_semantic_score * 0.25)
                    + (topic_score * 0.17)
                    + (0.18 if cross_lingual_match else 0.0)
                    + intent_bonus
                )

            # Apply entity/version mismatch penalty
            final_score = round(min(max(raw_score * ev_penalty, 0.0), 1.0), 3)
            item.relevance_score = final_score

            # Relevance Tier Classification (aligned with Part 6)
            if has_mismatch or final_score < 0.20:
                match_tier = "irrelevant" if final_score < 0.20 else "weakly_relevant"
            elif final_score >= 0.80:
                match_tier = "highly_relevant"
            elif final_score >= 0.55:
                match_tier = "relevant"
            elif final_score >= 0.35:
                match_tier = "partially_relevant"
            else:
                match_tier = "weakly_relevant"

            # Explainable Match Reasons (strictly factual from observed signals)
            reasons = list(ev_reasons)
            if title_score >= 0.70:
                reasons.append("Strong title match")
            elif title_score >= 0.40:
                reasons.append("Partial title match")
            if has_description and desc_score >= 0.50:
                reasons.append("Direct match in description")
            elif not has_description:
                reasons.append("Metadata-only result (no description available)")
            if qa.qualifiers and qualifier_hits > 0:
                reasons.append(f"Covers query qualifier: {', '.join(qa.qualifiers)}")
            elif qa.qualifiers and matched_entities and qualifier_hits == 0:
                reasons.append(f"Related subject, does not directly cover: {', '.join(qa.qualifiers)}")
            if cross_lingual_match:
                reasons.append("Cross-lingual concept match")
            if not reasons and final_score >= MIN_RELEVANCE_THRESHOLD:
                reasons.append("Contextual lexical/semantic match")

            meta["match_tier"] = match_tier
            meta["is_relevant"] = final_score >= MIN_RELEVANCE_THRESHOLD
            meta["matched_entities"] = matched_entities
            meta["match_reasons"] = reasons[:4]
            meta["match_breakdown"] = {
                "title": round(title_score * 100),
                "description": round(desc_score * 100),
                "topic": round(topic_score * 100),
                "semantic": round(lexical_semantic_score * 100),
                "entity_version": round(ev_score * 100) if qa.entities else None,
            }
            meta["query_intent"] = qa.intent
            meta["evidence_excerpt"] = cls._extract_best_passage(q_tokens_set, item.title or "", desc_text)
            item.metadata_fields = meta

        # Always return sorted Highest Match -> Lowest Match
        items.sort(key=lambda x: (-x.relevance_score, x.id))
        return items

    @staticmethod
    def sort_results(items: List[ResearchResult], sort_by: str = "relevant") -> List[ResearchResult]:
        """
        Deterministic sorting supporting:
          - 'relevant' (DEFAULT): Highest Match -> Lowest Match, recency as secondary tie-breaker.
          - 'newest': Newest to oldest by UTC published_at; unknown dates strictly AFTER dated records.
          - 'oldest': Oldest to newest by UTC published_at; unknown dates strictly AFTER dated records.
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

        if sort_by == "newest":
            dated = [x for x in items if x.published_at is not None]
            undated = [x for x in items if x.published_at is None]
            dated.sort(key=lambda x: (-_ts(x), -x.relevance_score, x.id))
            undated.sort(key=lambda x: (-x.relevance_score, x.id))
            return dated + undated
        elif sort_by == "oldest":
            dated = [x for x in items if x.published_at is not None]
            undated = [x for x in items if x.published_at is None]
            dated.sort(key=lambda x: (_ts(x), -x.relevance_score, x.id))
            undated.sort(key=lambda x: (-x.relevance_score, x.id))
            return dated + undated
        else:
            # Default: 'relevant' — Highest Match -> Lowest Match
            return sorted(items, key=lambda x: (-x.relevance_score, -_ts(x), x.id))
