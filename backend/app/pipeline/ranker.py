import math
import re
from typing import List, Dict, Any
from app.models.database import ResearchResult
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

class Ranker:
    @staticmethod
    def _extract_tokens(text: str) -> List[str]:
        return [w.lower() for w in re.findall(r'\b[a-zA-Z0-9]{3,}\b', text)]

    @classmethod
    def rank(cls, query: str, items: List[ResearchResult], mode: str = "general") -> List[ResearchResult]:
        if not items:
            return items

        # Build corpus: query + each item's title & content
        corpus = [query]
        for item in items:
            text = f"{item.title} {item.content_snippet or ''}"
            corpus.append(text)

        # 1. TF-IDF Cosine Similarity
        try:
            vectorizer = TfidfVectorizer(stop_words="english", max_features=1000)
            tfidf_matrix = vectorizer.fit_transform(corpus)
            query_vec = tfidf_matrix[0:1]
            doc_vecs = tfidf_matrix[1:]
            sims = cosine_similarity(query_vec, doc_vecs)[0]
        except Exception:
            sims = np.zeros(len(items))

        # Query token set for direct overlap
        q_tokens = set(cls._extract_tokens(query))

        for idx, item in enumerate(items):
            tfidf_score = float(sims[idx]) if idx < len(sims) else 0.0

            # 2. Query Term Overlap in Title
            title_tokens = set(cls._extract_tokens(item.title))
            overlap_count = len(q_tokens.intersection(title_tokens))
            title_overlap_ratio = overlap_count / max(len(q_tokens), 1)

            # 3. Engagement / Authority bonus
            engagement_bonus = 0.0
            if item.engagement_metrics:
                pts = item.engagement_metrics.get("points") or item.engagement_metrics.get("score") or 0
                comments = item.engagement_metrics.get("comments_count") or item.engagement_metrics.get("comments") or 0
                views = item.engagement_metrics.get("view_count") or 0
                raw_eng = pts + (comments * 2) + (views * 0.01)
                if raw_eng > 0:
                    engagement_bonus = min(math.log10(raw_eng + 1) * 0.08, 0.25)

            # 4. Mode-specific weighting
            mode_multiplier = 1.0
            if mode == "problem_discovery":
                # Boost issues, discussions, questions mentioning problem keywords
                problem_keywords = {"bug", "issue", "problem", "fail", "error", "broken", "limitation", "complaint", "difficult", "struggle", "fix"}
                content_lower = f"{item.title} {item.content_snippet or ''}".lower()
                matches = sum(1 for kw in problem_keywords if kw in content_lower)
                if matches > 0:
                    mode_multiplier = 1.0 + min(matches * 0.1, 0.4)
            elif mode == "technical":
                if item.source_name in ("github", "stackexchange", "arxiv", "openalex", "crossref", "kaggle", "internet_archive"):
                    mode_multiplier = 1.2

            # Final normalized relevance score between 0.0 and 1.0
            raw_score = (tfidf_score * 0.55) + (title_overlap_ratio * 0.30) + engagement_bonus
            final_score = round(min(max(raw_score * mode_multiplier, 0.05), 1.0), 3)

            item.relevance_score = final_score

        # Sort descending by relevance score
        items.sort(key=lambda x: x.relevance_score, reverse=True)
        return items
