from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from pydantic import BaseModel, Field


def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode("utf-8")).hexdigest()[:16]


class RawItem(BaseModel):
    """One item as fetched from a source connector, before classification."""

    id: str = ""
    source: str
    category: str
    title: str
    url: str
    published_at: datetime
    summary: str = ""
    raw_content: str = ""
    meta: dict = Field(default_factory=dict)

    def model_post_init(self, __context) -> None:
        if not self.id:
            self.id = url_hash(self.url)


class ClassifiedItem(RawItem):
    is_relevant: bool = True
    topic: str = ""  # core / cncf / security / ecosystem / cloud / emerging


class Story(BaseModel):
    """A cluster of one or more ClassifiedItems covering the same event."""

    id: str
    canonical_url: str
    title: str
    topic: str
    items: list[ClassifiedItem]
    published_at: datetime
    score: float = 0.0
    summary: str = ""


class TrendSignal(BaseModel):
    label: str
    detail: str


class Briefing(BaseModel):
    date: str
    top_stories: list[Story]
    category_counts: dict[str, int]
    trend_signals: list[TrendSignal]
    what_changed: str
    watch_tomorrow: str
    linkedin_text: str = ""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
