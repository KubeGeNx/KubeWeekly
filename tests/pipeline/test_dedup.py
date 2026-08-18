from __future__ import annotations

from datetime import datetime, timezone

from kubeweekly.pipeline.dedup import cluster_stories
from tests.conftest import make_classified_item


def test_near_duplicate_titles_cluster_together():
    items = [
        make_classified_item(
            title="Kubernetes 1.34 released with new scheduler features",
            url="https://a.example.com/1",
            source="Blog A",
            published_at=datetime(2026, 8, 15, 9, 0, tzinfo=timezone.utc),
        ),
        make_classified_item(
            title="Kubernetes 1.34 released: new scheduler features",
            url="https://b.example.com/1",
            source="Blog B",
            published_at=datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc),
        ),
    ]

    stories = cluster_stories(items)

    assert len(stories) == 1
    assert len(stories[0].items) == 2
    assert stories[0].canonical_url == "https://a.example.com/1"  # earliest wins


def test_distinct_titles_do_not_cluster():
    items = [
        make_classified_item(title="Kubernetes 1.34 released", url="https://a.example.com/1"),
        make_classified_item(title="CVE-2026-1234 found in kubelet", url="https://b.example.com/2"),
    ]

    stories = cluster_stories(items)

    assert len(stories) == 2


def test_irrelevant_items_excluded():
    items = [
        make_classified_item(title="Relevant story", url="https://a.example.com/1", is_relevant=True),
        make_classified_item(title="Irrelevant story", url="https://b.example.com/2", is_relevant=False),
    ]

    stories = cluster_stories(items)

    assert len(stories) == 1
    assert stories[0].title == "Relevant story"
