from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from kubeweekly.models import ClassifiedItem, RawItem

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def make_raw_item(**overrides) -> RawItem:
    defaults = dict(
        source="test-source",
        category="core",
        title="Example Kubernetes item",
        url="https://example.com/item",
        published_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
        summary="An example summary.",
    )
    defaults.update(overrides)
    return RawItem(**defaults)


def make_classified_item(**overrides) -> ClassifiedItem:
    defaults = dict(is_relevant=True, topic="core")
    raw_kwargs = {k: v for k, v in overrides.items() if k not in defaults}
    item = make_raw_item(**raw_kwargs)
    defaults.update({k: v for k, v in overrides.items() if k in defaults})
    return ClassifiedItem(**item.model_dump(), **defaults)


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR
