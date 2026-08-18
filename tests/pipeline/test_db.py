from __future__ import annotations

from datetime import datetime, timedelta, timezone

from kubeweekly.db import Database
from kubeweekly.models import ClassifiedItem
from tests.conftest import make_raw_item


def test_upsert_raw_item_is_idempotent():
    db = Database(":memory:")
    item = make_raw_item(url="https://example.com/a")
    now = datetime.now(timezone.utc)

    assert db.upsert_raw_item(item, now) is True
    assert db.upsert_raw_item(item, now) is False

    assert len(db.unclassified_items()) == 1


def test_mark_classified_then_query_relevant_since():
    db = Database(":memory:")
    now = datetime.now(timezone.utc)
    recent = make_raw_item(url="https://example.com/recent", published_at=now)
    old = make_raw_item(url="https://example.com/old", published_at=now - timedelta(days=10))

    db.upsert_raw_item(recent, now)
    db.upsert_raw_item(old, now)

    for raw in (recent, old):
        db.mark_classified(ClassifiedItem(**raw.model_dump(), is_relevant=True, topic="core"))

    assert db.unclassified_items() == []

    relevant = db.relevant_items_since(now - timedelta(days=1))
    assert len(relevant) == 1
    assert relevant[0].url == "https://example.com/recent"


def test_irrelevant_items_excluded_from_relevant_query():
    db = Database(":memory:")
    now = datetime.now(timezone.utc)
    item = make_raw_item(url="https://example.com/spam", published_at=now)
    db.upsert_raw_item(item, now)
    db.mark_classified(ClassifiedItem(**item.model_dump(), is_relevant=False, topic=""))

    assert db.relevant_items_since(now - timedelta(days=1)) == []
