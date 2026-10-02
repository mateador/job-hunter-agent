from collections import Counter

import pytest
from pydantic import ValidationError

from evals.dataset_schema import GoldenDataset, GoldenQuery, load_dataset


@pytest.fixture(scope="module")
def dataset():
    return load_dataset()


def test_dataset_loads_with_20_queries(dataset):
    assert len(dataset.queries) == 20


def test_category_counts(dataset):
    counts = Counter(q.category for q in dataset.queries)
    assert counts == {"standard": 6, "niche": 4, "broad": 3, "edge_case": 4, "agency": 3}


def test_ids_are_unique(dataset):
    ids = [q.id for q in dataset.queries]
    assert len(ids) == len(set(ids))


def test_duplicate_ids_rejected():
    q = dict(id="a", query="x", category="broad", description="d")
    with pytest.raises(ValidationError):
        GoldenDataset(version="1", queries=[q, q])


def test_invalid_tool_rejected():
    with pytest.raises(ValidationError):
        GoldenQuery(id="a", query="x", category="broad", description="d", expected_tools=["google"])


def test_non_edge_cases_have_relevance_keywords(dataset):
    missing = [q.id for q in dataset.queries
               if q.category != "edge_case" and not q.relevance_keywords]
    assert missing == []


def test_agency_queries_expect_agency_flag(dataset):
    assert all(q.expect_agency_flag for q in dataset.by_category()["agency"])


def test_cv_path_is_optional_and_mixed(dataset):
    with_cv = [q for q in dataset.queries if q.cv_path]
    assert 0 < len(with_cv) < len(dataset.queries)
