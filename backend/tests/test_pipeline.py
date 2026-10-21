import pytest
from app.connectors.base import RawResult
from app.pipeline.normalizer import Normalizer
from app.pipeline.deduplicator import Deduplicator
from app.pipeline.ranker import Ranker

def test_normalizer_url_and_text():
    raw = RawResult(
        source_name="web_search",
        title="  Awesome   AI Tool For Research  \n",
        content_snippet="Discover fast   insights... ",
        source_url="https://example.com/item?utm_source=twitter&utm_medium=cpc&id=123#ref",
        author=" Researcher "
    )
    res = Normalizer.normalize(raw, "test_job_123")
    assert res.title == "Awesome AI Tool For Research"
    assert res.content_snippet == "Discover fast insights..."
    assert res.source_url == "https://example.com/item?id=123"
    assert res.author == "Researcher"
    assert res.is_duplicate is False

def test_deduplicator_exact_url_and_title():
    raw1 = RawResult(source_name="hackernews", title="Python 3.12 release notes", source_url="https://python.org/release/3.12")
    raw2 = RawResult(source_name="web_search", title="Python 3.12 Release Notes!", source_url="https://python.org/release/3.12")
    raw3 = RawResult(source_name="reddit", title="Python 3.12 release notes", source_url="https://reddit.com/r/python/item")

    item1 = Normalizer.normalize(raw1, "job1")
    item2 = Normalizer.normalize(raw2, "job1")
    item3 = Normalizer.normalize(raw3, "job1")

    deduped = Deduplicator.deduplicate([item1, item2, item3])
    assert deduped[0].is_duplicate is False
    assert deduped[1].is_duplicate is True # duplicate URL
    assert deduped[2].is_duplicate is True # duplicate title

def test_ranker_problem_discovery_boost():
    raw1 = RawResult(
        source_name="github",
        title="Error bug: memory leak in model training",
        content_snippet="Users experience critical memory failure and crashing during loop",
        source_url="https://github.com/test/repo/issues/1",
        engagement_metrics={"reactions_total": 15}
    )
    raw2 = RawResult(
        source_name="wikipedia",
        title="Machine Learning Overview",
        content_snippet="Machine learning is a field of inquiry devoted to understanding data",
        source_url="https://en.wikipedia.org/wiki/Machine_learning"
    )

    item1 = Normalizer.normalize(raw1, "job2")
    item2 = Normalizer.normalize(raw2, "job2")

    ranked = Ranker.rank("machine learning memory leak bug", [item2, item1], mode="problem_discovery")
    # item1 should rank first due to problem terms overlap and query relevance
    assert ranked[0].id == item1.id
    assert ranked[0].relevance_score > ranked[1].relevance_score
