from __future__ import annotations

from datetime import datetime, timedelta, timezone

from kubeweekly.models import Story
from kubeweekly.pipeline.score import _heuristic_score
from tests.conftest import make_classified_item


def _story(topic: str, published_at: datetime, n_items: int = 1, stars: int = 0) -> Story:
    items = [
        make_classified_item(topic=topic, published_at=published_at, url=f"https://example.com/{i}")
        for i in range(n_items)
    ]
    if stars:
        items[0].meta["stars"] = stars
    return Story(
        id="s1",
        canonical_url=items[0].url,
        title="Test story",
        topic=topic,
        items=items,
        published_at=published_at,
    )


def test_security_scores_higher_than_ecosystem_for_same_recency():
    now = datetime.now(timezone.utc)
    security = _story("security", now)
    ecosystem = _story("ecosystem", now)

    assert _heuristic_score(security) > _heuristic_score(ecosystem)


def test_recent_story_scores_higher_than_old_story():
    now = datetime.now(timezone.utc)
    recent = _story("core", now)
    old = _story("core", now - timedelta(days=10))

    assert _heuristic_score(recent) > _heuristic_score(old)


def test_multi_source_cluster_scores_higher():
    now = datetime.now(timezone.utc)
    single = _story("core", now, n_items=1)
    multi = _story("core", now, n_items=4)

    assert _heuristic_score(multi) > _heuristic_score(single)


def test_star_velocity_increases_score():
    now = datetime.now(timezone.utc)
    no_stars = _story("emerging", now, stars=0)
    popular = _story("emerging", now, stars=500)

    assert _heuristic_score(popular) > _heuristic_score(no_stars)
