from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from kubeweekly.db import Database
from kubeweekly.models import Story, TrendSignal

ROLLING_WINDOW_DAYS = 7


def detect_trends(
    stories: list[Story], db: Database, now: datetime | None = None
) -> tuple[list[TrendSignal], str]:
    now = now or datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    window_start = today_start - timedelta(days=ROLLING_WINDOW_DAYS)

    today_counts = Counter(s.topic for s in stories)
    yesterday_counts = db.story_counts_by_topic(yesterday_start, today_start)
    window_counts = db.story_counts_by_topic(window_start, today_start)

    what_changed = _describe_delta(today_counts, yesterday_counts)
    signals = _emerging_signals(stories, window_counts)

    return signals, what_changed


def _describe_delta(today: Counter, yesterday: dict[str, int]) -> str:
    parts = []
    for topic in sorted(set(today) | set(yesterday)):
        t, y = today.get(topic, 0), yesterday.get(topic, 0)
        if t == y:
            continue
        arrow = "up" if t > y else "down"
        parts.append(f"{topic} {arrow} ({y}→{t})")
    if not parts:
        return "Roughly steady across categories compared to yesterday."
    return "; ".join(parts)


def _emerging_signals(stories: list[Story], window_counts: dict[str, int]) -> list[TrendSignal]:
    signals: list[TrendSignal] = []

    emerging = [s for s in stories if s.topic == "emerging"]
    emerging.sort(key=lambda s: s.score, reverse=True)
    for story in emerging[:3]:
        stars = max((i.meta.get("stars", 0) for i in story.items), default=0)
        detail = f"{story.title}"
        if stars:
            detail += f" ({stars}★)"
        signals.append(TrendSignal(label="Gaining momentum", detail=detail))

    window_avg_per_day = {
        topic: count / ROLLING_WINDOW_DAYS for topic, count in window_counts.items()
    }
    today_counts = Counter(s.topic for s in stories)
    for topic, count in today_counts.items():
        avg = window_avg_per_day.get(topic, 0)
        if avg > 0 and count >= avg * 2 and count >= 3:
            signals.append(
                TrendSignal(
                    label="Volume spike",
                    detail=f"{topic}: {count} stories today vs {avg:.1f}/day avg over last {ROLLING_WINDOW_DAYS}d",
                )
            )

    return signals
