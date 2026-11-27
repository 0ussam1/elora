"""
Search Quality & Intelligence Evaluation Suite for ELORA.

Tests Query Understanding, Hybrid Ranking, Entity/Version Disambiguation,
Chronological UTC Sorting, Cross-Source DOI Deduplication, Multilingual Matching
(EN / FR / AR), and IR metrics (Precision@5, Precision@10, MRR, NDCG@10).
"""
import math
from datetime import datetime, timezone, timedelta
import pytest

from app.connectors.base import RawResult
from app.pipeline.normalizer import Normalizer
from app.pipeline.deduplicator import Deduplicator
from app.pipeline.query_analyzer import QueryAnalyzer
from app.pipeline.ranker import Ranker, MIN_RELEVANCE_THRESHOLD


def _ndcg_at_k(relevances: list[int], k: int) -> float:
    rel_k = relevances[:k]
    dcg = sum(r / math.log2(i + 2) for i, r in enumerate(rel_k))
    ideal = sorted(relevances, reverse=True)[:k]
    idcg = sum(r / math.log2(i + 2) for i, r in enumerate(ideal))
    return dcg / idcg if idcg > 0 else 0.0


class TestQueryUnderstanding:
    def test_twelve_benchmark_queries_analysis(self):
        queries = [
            ("GTA 6", "en", "gta", "6"),
            ("GTA 5", "en", "gta", "5"),
            ("GTA 6 release date", "en", "gta", "6"),
            ("GTA 6 vs GTA 5", "en", "gta", "6"),
            ("Python 3.13", "en", "python", "3.13"),
            ("Windows 11", "en", "windows", "11"),
            ("iPhone 17", "en", "iphone", "17"),
            ("GPT-6", "en", "gpt", "6"),
            ("Latest artificial intelligence research", "en", None, None),
            ("Machine learning security", "en", None, None),
            ("Intelligence artificielle", "fr", None, None),
            ("الذكاء الاصطناعي", "ar", None, None),
        ]
        for q, expected_lang, exp_ent, exp_ver in queries:
            qa = QueryAnalyzer.analyze(q)
            assert qa.language == expected_lang, f"Language mismatch for {q}: {qa.language}"
            if exp_ent:
                assert any(e.entity == exp_ent and e.version == exp_ver for e in qa.entities), (
                    f"Missing entity/version ({exp_ent} {exp_ver}) in {q}: {qa.entities}"
                )

        # Comparison intent check
        qa_cmp = QueryAnalyzer.analyze("GTA 6 vs GTA 5")
        assert qa_cmp.is_comparison is True
        assert qa_cmp.intent == "comparison"
        assert len(qa_cmp.entities) == 2

        # Multilingual expansions check
        qa_fr = QueryAnalyzer.analyze("Intelligence artificielle")
        assert "artificial intelligence" in qa_fr.multilingual_expansions
        qa_ar = QueryAnalyzer.analyze("الذكاء الاصطناعي")
        assert "artificial intelligence" in qa_ar.multilingual_expansions


class TestEntityVersionAndRelevance:
    def test_gta6_does_not_rank_gta5_high(self):
        raw_exact = RawResult(
            source_name="web_search",
            title="GTA 6 Official Trailer 2 and Release Date Details",
            content_snippet="Rockstar Games confirms GTA 6 launch window and Vice City map.",
            source_url="https://example.com/gta-6-news",
        )
        raw_wrong = RawResult(
            source_name="reddit",
            title="GTA 5 Online Weekly Update and Best Cars",
            content_snippet="GTA 5 players can earn double money in GTA Online this week.",
            source_url="https://reddit.com/r/gta5/weekly",
        )
        raw_irrelevant = RawResult(
            source_name="wikipedia",
            title="Photosynthesis in Tropical Plants",
            content_snippet="Chloroplasts convert sunlight into chemical energy.",
            source_url="https://en.wikipedia.org/wiki/Photosynthesis",
        )
        items = [Normalizer.normalize(r, "j1") for r in (raw_wrong, raw_irrelevant, raw_exact)]
        exact_id = items[2].id
        ranked = Ranker.rank("GTA 6", items)

        assert ranked[0].id == exact_id  # GTA 6 exact match is #1
        assert ranked[0].relevance_score > ranked[1].relevance_score
        # GTA 5 must be heavily penalized for version mismatch
        wrong_item = next(x for x in ranked if "GTA 5" in x.title)
        assert wrong_item.relevance_score < ranked[0].relevance_score * 0.5
        # Irrelevant item must be below minimum threshold
        irrel_item = next(x for x in ranked if "Photosynthesis" in x.title)
        assert irrel_item.relevance_score < MIN_RELEVANCE_THRESHOLD

    def test_comparison_query_keeps_both_versions_relevant(self):
        raw_both = RawResult(
            source_name="web_search",
            title="GTA 6 vs GTA 5: Graphics and Map Size Comparison",
            content_snippet="Comparing GTA 6 Vice City against GTA 5 Los Santos.",
            source_url="https://example.com/gta6-vs-gta5",
        )
        raw_other = RawResult(
            source_name="web_search",
            title="Best Cooking Recipes 2025",
            content_snippet="Simple pasta and salad recipes.",
            source_url="https://example.com/recipes",
        )
        items = [Normalizer.normalize(r, "j2") for r in (raw_other, raw_both)]
        both_id = items[1].id
        ranked = Ranker.rank("GTA 6 vs GTA 5", items)
        assert ranked[0].id == both_id
        assert ranked[0].relevance_score >= 0.55

    def test_python_313_vs_311(self):
        raw_313 = RawResult(
            source_name="github",
            title="Python 3.13 Free-Threaded Memory Management",
            content_snippet="PEP 703 GIL removal and memory management improvements in Python 3.13.",
            source_url="https://github.com/python/cpython/issues/313",
        )
        raw_311 = RawResult(
            source_name="stackexchange",
            title="Python 3.11 Dictionary Memory Optimization",
            content_snippet="How Python 3.11 reduced dictionary memory overhead.",
            source_url="https://stackoverflow.com/q/311",
        )
        items = [Normalizer.normalize(r, "j3") for r in (raw_311, raw_313)]
        target_id = items[1].id
        ranked = Ranker.rank("Python 3.13 memory management", items)
        assert ranked[0].id == target_id
        assert ranked[0].relevance_score > ranked[1].relevance_score

    def test_multilingual_french_and_arabic_match_english_docs(self):
        raw_ai = RawResult(
            source_name="arxiv",
            title="Advances in Artificial Intelligence and Neural Reasoning",
            content_snippet="A comprehensive survey of modern artificial intelligence systems.",
            source_url="https://arxiv.org/abs/2501.00001",
        )
        raw_irrel = RawResult(
            source_name="wikipedia",
            title="History of Medieval Architecture",
            content_snippet="Gothic cathedrals in Europe.",
            source_url="https://en.wikipedia.org/wiki/Gothic_architecture",
        )

        # French query
        items_fr = [Normalizer.normalize(r, "jfr") for r in (raw_irrel, raw_ai)]
        ai_fr_id = items_fr[1].id
        ranked_fr = Ranker.rank("Intelligence artificielle", items_fr)
        assert ranked_fr[0].id == ai_fr_id
        assert ranked_fr[0].relevance_score > ranked_fr[1].relevance_score

        # Arabic query
        items_ar = [Normalizer.normalize(r, "jar") for r in (raw_irrel, raw_ai)]
        ai_ar_id = items_ar[1].id
        ranked_ar = Ranker.rank("الذكاء الاصطناعي", items_ar)
        assert ranked_ar[0].id == ai_ar_id
        assert ranked_ar[0].relevance_score > ranked_ar[1].relevance_score


class TestChronologicalSortingAndDates:
    def test_utc_date_normalization_rejects_invalid_future_dates(self):
        future_dt = datetime.now(timezone.utc) + timedelta(days=365)
        raw_bad = RawResult(
            source_name="web_search",
            title="Future Glitch Article",
            source_url="https://example.com/future",
            published_at=future_dt,
        )
        norm = Normalizer.normalize(raw_bad, "jd1")
        assert norm.published_at is None
        assert norm.metadata_fields["date_status"] == "missing_date"

    def test_newest_first_default_places_undated_after_dated(self):
        now = datetime.now(timezone.utc)
        r_old = Normalizer.normalize(RawResult(
            source_name="arxiv", title="Old Paper", source_url="https://arxiv.org/1",
            published_at=now - timedelta(days=100)
        ), "js")
        r_new = Normalizer.normalize(RawResult(
            source_name="arxiv", title="New Paper", source_url="https://arxiv.org/2",
            published_at=now - timedelta(days=2)
        ), "js")
        r_none = Normalizer.normalize(RawResult(
            source_name="web_search", title="Undated Page", source_url="https://example.com/3",
            published_at=None
        ), "js")

        sorted_newest = Ranker.sort_results([r_none, r_old, r_new], sort_by="newest")
        assert [x.title for x in sorted_newest] == ["New Paper", "Old Paper", "Undated Page"]

        sorted_oldest = Ranker.sort_results([r_none, r_old, r_new], sort_by="oldest")
        assert [x.title for x in sorted_oldest] == ["Old Paper", "New Paper", "Undated Page"]


class TestCrossSourceDeduplication:
    def test_doi_dedup_merges_provenance_and_never_merges_versions(self):
        r1 = Normalizer.normalize(RawResult(
            source_name="openalex",
            title="Attention Is All You Need",
            content_snippet="Short abstract.",
            source_url="https://openalex.org/W123",
            metadata={"doi": "10.5555/3295222.3295349"},
        ), "jd")
        r2 = Normalizer.normalize(RawResult(
            source_name="crossref",
            title="Attention Is All You Need",
            content_snippet="Much richer abstract explaining the Transformer architecture in full detail.",
            source_url="https://doi.org/10.5555/3295222.3295349",
            metadata={"doi": "https://doi.org/10.5555/3295222.3295349"},
        ), "jd")
        r3_gta6 = Normalizer.normalize(RawResult(
            source_name="web_search",
            title="Grand Theft Auto 6 Official Release Window",
            source_url="https://example.com/gta6",
        ), "jd")
        r4_gta5 = Normalizer.normalize(RawResult(
            source_name="web_search",
            title="Grand Theft Auto 5 Official Release Window",
            source_url="https://example.com/gta5",
        ), "jd")

        deduped = Deduplicator.deduplicate([r1, r2, r3_gta6, r4_gta5])
        assert deduped[0].is_duplicate is False
        assert deduped[1].is_duplicate is True
        assert deduped[1].duplicate_of == deduped[0].id
        assert len(deduped[0].metadata_fields["also_found_in"]) == 1
        assert "Transformer architecture" in deduped[0].content_snippet
        # Distinct versions MUST NOT be merged
        assert deduped[2].is_duplicate is False
        assert deduped[3].is_duplicate is False


class TestEvaluationMetrics:
    def test_ir_metrics_precision_mrr_ndcg(self):
        docs = [
            ("Python 3.13 Free-Threaded Mode Guide", "New Python 3.13 memory management and GIL.", 1),
            ("Python 3.13 Release Notes", "Official Python 3.13 changelog and memory updates.", 1),
            ("Python 3.11 Old Performance Notes", "Python 3.11 benchmark results.", 0),
            ("Java Garbage Collection Overview", "JVM G1GC memory management.", 0),
            ("Cooking Pasta at Home", "Italian recipe guide.", 0),
        ]
        items = []
        rel_map = {}
        for i, (t, s, rel) in enumerate(docs):
            nr = Normalizer.normalize(RawResult(
                source_name="github", title=t, content_snippet=s, source_url=f"https://example.com/{i}"
            ), "jeval")
            items.append(nr)
            rel_map[nr.id] = rel

        ranked = Ranker.rank("Python 3.13 memory management", items)
        rels = [rel_map[x.id] for x in ranked]
        p_at_2 = sum(rels[:2]) / 2.0
        ndcg_5 = _ndcg_at_k(rels, 5)
        mrr = next((1.0 / (idx + 1) for idx, r in enumerate(rels) if r == 1), 0.0)

        assert p_at_2 == 1.0
        assert ndcg_5 >= 0.95
        assert mrr == 1.0
