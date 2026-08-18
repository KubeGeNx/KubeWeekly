from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from kubeweekly.llm import LLMClient
from kubeweekly.models import Story

log = logging.getLogger(__name__)

BATCH_SIZE = 20

TOPIC_WEIGHT = {
    "core": 30,
    "security": 25,
    "cncf": 20,
    "cloud": 15,
    "ecosystem": 15,
    "emerging": 10,
}

SYSTEM_PROMPT = """You score Kubernetes/CNCF ecosystem news for a technical
audience of platform engineers and SREs.

For each story, give an "impact" score from 0-20:
- 15-20: breaking change, major security issue, or something most K8s users
  should act on or know about immediately.
- 8-14: solid, useful development worth knowing about.
- 0-7: minor, routine, or low real-world impact.

Respond with ONLY a JSON array, no prose:
[{"id": "<story id>", "impact": 12}, ...]
"""


def score_stories(client: LLMClient, stories: list[Story], model: str) -> list[Story]:
    for story in stories:
        story.score = _heuristic_score(story)

    for i in range(0, len(stories), BATCH_SIZE):
        batch = stories[i : i + BATCH_SIZE]
        try:
            impacts = _llm_impact_batch(client, batch, model)
        except Exception:
            log.warning("score: LLM impact batch failed, using heuristic score only", exc_info=True)
            impacts = {}
        for story in batch:
            story.score = min(100.0, story.score + impacts.get(story.id, 0))

    stories.sort(key=lambda s: s.score, reverse=True)
    return stories


def _heuristic_score(story: Story) -> float:
    score = TOPIC_WEIGHT.get(story.topic, 10)

    age_hours = (datetime.now(timezone.utc) - story.published_at).total_seconds() / 3600
    score += max(0, 20 - (age_hours / 72) * 20)

    score += min(len(story.items) - 1, 5) * 3

    max_stars = max((item.meta.get("stars", 0) for item in story.items), default=0)
    score += min(max_stars / 50, 15)

    return round(score, 1)


def _llm_impact_batch(client: LLMClient, batch: list[Story], model: str) -> dict[str, int]:
    payload = [{"id": s.id, "title": s.title, "topic": s.topic} for s in batch]
    text = client.complete(
        system=SYSTEM_PROMPT, user_content=json.dumps(payload), max_tokens=1024, model=model
    )
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        return {}
    try:
        decisions = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return {d["id"]: int(d.get("impact", 0)) for d in decisions if "id" in d}
