from __future__ import annotations

import json
import logging
from collections import defaultdict

from kubeweekly.llm import LLMClient
from kubeweekly.models import Story

log = logging.getLogger(__name__)

BATCH_SIZE = 10
TOP_PER_TOPIC = 4

SYSTEM_PROMPT = """You write terse, technical "why it matters" blurbs for a
Kubernetes/CNCF news briefing aimed at platform engineers.

For each story, write ONE sentence (max ~30 words) explaining concretely why
a platform engineer should care - the practical consequence, not a
restatement of the headline. No hedging, no "this is important because" -
just the substance.

Respond with ONLY a JSON array, no prose:
[{"id": "<story id>", "summary": "..."}]
"""


def select_top_stories(stories: list[Story], per_topic: int = TOP_PER_TOPIC) -> list[Story]:
    by_topic: dict[str, list[Story]] = defaultdict(list)
    for story in sorted(stories, key=lambda s: s.score, reverse=True):
        by_topic[story.topic].append(story)

    selected: list[Story] = []
    for topic_stories in by_topic.values():
        selected.extend(topic_stories[:per_topic])
    selected.sort(key=lambda s: s.score, reverse=True)
    return selected


def summarize_stories(client: LLMClient, stories: list[Story], model: str) -> None:
    """Fills in `story.summary` in place for the given stories."""
    for i in range(0, len(stories), BATCH_SIZE):
        batch = stories[i : i + BATCH_SIZE]
        try:
            summaries = _summarize_batch(client, batch, model)
        except Exception:
            log.warning("summarize: batch failed, falling back to titles", exc_info=True)
            summaries = {}
        for story in batch:
            story.summary = summaries.get(story.id, story.title)


def _summarize_batch(client: LLMClient, batch: list[Story], model: str) -> dict[str, str]:
    payload = [
        {
            "id": s.id,
            "title": s.title,
            "topic": s.topic,
            "sources": [i.source for i in s.items],
            "excerpt": (s.items[0].summary or "")[:500],
        }
        for s in batch
    ]
    text = client.complete(
        system=SYSTEM_PROMPT, user_content=json.dumps(payload), max_tokens=2048, model=model
    )
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        return {}
    try:
        decisions = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return {d["id"]: d["summary"] for d in decisions if "id" in d and "summary" in d}
