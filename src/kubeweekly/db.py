from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from kubeweekly.models import ClassifiedItem, RawItem, Story

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_items (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    published_at TEXT NOT NULL,
    summary TEXT,
    raw_content TEXT,
    meta TEXT,
    is_relevant INTEGER,
    topic TEXT,
    first_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stories (
    id TEXT PRIMARY KEY,
    canonical_url TEXT NOT NULL,
    title TEXT NOT NULL,
    topic TEXT NOT NULL,
    item_ids TEXT NOT NULL,
    published_at TEXT NOT NULL,
    score REAL NOT NULL,
    summary TEXT,
    briefing_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS briefings (
    briefing_date TEXT PRIMARY KEY,
    linkedin_text TEXT NOT NULL,
    category_counts TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_raw_items_published ON raw_items(published_at);
CREATE INDEX IF NOT EXISTS idx_stories_briefing_date ON stories(briefing_date);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    @contextmanager
    def cursor(self):
        cur = self._conn.cursor()
        try:
            yield cur
            self._conn.commit()
        finally:
            cur.close()

    def close(self) -> None:
        self._conn.close()

    def upsert_raw_item(self, item: RawItem, now: datetime) -> bool:
        """Insert if new. Returns True if the item was newly inserted."""
        with self.cursor() as cur:
            cur.execute("SELECT 1 FROM raw_items WHERE id = ?", (item.id,))
            if cur.fetchone():
                return False
            cur.execute(
                """
                INSERT INTO raw_items
                    (id, source, category, title, url, published_at, summary,
                     raw_content, meta, is_relevant, topic, first_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?)
                """,
                (
                    item.id,
                    item.source,
                    item.category,
                    item.title,
                    item.url,
                    item.published_at.isoformat(),
                    item.summary,
                    item.raw_content,
                    json.dumps(item.meta),
                    now.isoformat(),
                ),
            )
            return True

    def mark_classified(self, item: ClassifiedItem) -> None:
        with self.cursor() as cur:
            cur.execute(
                "UPDATE raw_items SET is_relevant = ?, topic = ? WHERE id = ?",
                (1 if item.is_relevant else 0, item.topic, item.id),
            )

    def unclassified_items(self) -> list[RawItem]:
        with self.cursor() as cur:
            cur.execute("SELECT * FROM raw_items WHERE is_relevant IS NULL")
            return [_row_to_raw_item(row) for row in cur.fetchall()]

    def relevant_items_since(self, since: datetime) -> list[ClassifiedItem]:
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM raw_items
                WHERE is_relevant = 1 AND published_at >= ?
                ORDER BY published_at DESC
                """,
                (since.isoformat(),),
            )
            return [_row_to_classified_item(row) for row in cur.fetchall()]

    def save_stories(self, stories: list[Story], briefing_date: str) -> None:
        with self.cursor() as cur:
            for story in stories:
                cur.execute(
                    """
                    INSERT OR REPLACE INTO stories
                        (id, canonical_url, title, topic, item_ids, published_at,
                         score, summary, briefing_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        story.id,
                        story.canonical_url,
                        story.title,
                        story.topic,
                        json.dumps([i.id for i in story.items]),
                        story.published_at.isoformat(),
                        story.score,
                        story.summary,
                        briefing_date,
                    ),
                )

    def story_counts_by_topic(self, since: datetime, until: datetime) -> dict[str, int]:
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT topic, COUNT(*) as n FROM stories
                WHERE published_at >= ? AND published_at < ?
                GROUP BY topic
                """,
                (since.isoformat(), until.isoformat()),
            )
            return {row["topic"]: row["n"] for row in cur.fetchall()}

    def save_briefing(self, briefing_date: str, linkedin_text: str, category_counts: dict) -> None:
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT OR REPLACE INTO briefings
                    (briefing_date, linkedin_text, category_counts, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    briefing_date,
                    linkedin_text,
                    json.dumps(category_counts),
                    datetime.utcnow().isoformat(),
                ),
            )


def _row_to_raw_item(row: sqlite3.Row) -> RawItem:
    return RawItem(
        id=row["id"],
        source=row["source"],
        category=row["category"],
        title=row["title"],
        url=row["url"],
        published_at=datetime.fromisoformat(row["published_at"]),
        summary=row["summary"] or "",
        raw_content=row["raw_content"] or "",
        meta=json.loads(row["meta"] or "{}"),
    )


def _row_to_classified_item(row: sqlite3.Row) -> ClassifiedItem:
    raw = _row_to_raw_item(row)
    return ClassifiedItem(
        **raw.model_dump(),
        is_relevant=bool(row["is_relevant"]),
        topic=row["topic"] or "",
    )
