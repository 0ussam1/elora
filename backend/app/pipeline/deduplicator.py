from typing import List, Set, Tuple
import re
from app.models.database import ResearchResult

class Deduplicator:
    @staticmethod
    def _simplify_title(title: str) -> str:
        # Lowercase, keep alphanumeric and single space
        return re.sub(r'[^a-z0-9\s]', '', title.lower()).strip()

    @classmethod
    def deduplicate(cls, items: List[ResearchResult]) -> List[ResearchResult]:
        seen_urls: Set[str] = set()
        seen_titles: Set[str] = set()

        for item in items:
            # Check 1: Canonical URL exact match
            if item.source_url in seen_urls:
                item.is_duplicate = True
                continue
            seen_urls.add(item.source_url)

            # Check 2: Normalized title exact match
            simplified = cls._simplify_title(item.title)
            if len(simplified) > 10 and simplified in seen_titles:
                item.is_duplicate = True
                continue
            if len(simplified) > 10:
                seen_titles.add(simplified)

        return items
