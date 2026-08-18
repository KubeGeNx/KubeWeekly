from __future__ import annotations

import json
import logging

from kubeweekly.llm import LLMClient
from kubeweekly.models import ClassifiedItem, RawItem

log = logging.getLogger(__name__)

BATCH_SIZE = 20
VALID_TOPICS = {"core", "cncf", "security", "ecosystem", "cloud", "emerging"}

SYSTEM_PROMPT = """You are a filter for a Kubernetes/CNCF ecosystem news pipeline.

For each item, decide:
- is_relevant: true only if the item is substantively about Kubernetes, a CNCF
  project, or a widely-used Kubernetes ecosystem tool (Helm, operators,
  service mesh, GitOps, container runtimes, etc). False for items that only
  incidentally mention "kubernetes"/"k8s" as a keyword (e.g. a generic devops
  listicle, an unrelated product announcement, spam).
- topic: one of "core" (Kubernetes project itself, KEPs, releases),
  "cncf" (CNCF projects/governance), "security" (CVEs, vulnerabilities),
  "ecosystem" (Helm charts, operators, vendor tools), "cloud"
  (AWS/GCP/Azure managed Kubernetes), "emerging" (new/trending projects,
  discussion threads).

Respond with ONLY a JSON array, no prose, no markdown fences:
[{"id": "<item id>", "is_relevant": true, "topic": "core"}, ...]
"""


def classify_items(client: LLMClient, items: list[RawItem], model: str) -> list[ClassifiedItem]:
    classified: list[ClassifiedItem] = []
    for i in range(0, len(items), BATCH_SIZE):
        batch = items[i : i + BATCH_SIZE]
        try:
            classified.extend(_classify_batch(client, batch, model))
        except Exception:
            log.warning("classify: batch failed, marking as not relevant", exc_info=True)
            classified.extend(ClassifiedItem(**item.model_dump(), is_relevant=False, topic="") for item in batch)
    return classified


def _classify_batch(client: LLMClient, batch: list[RawItem], model: str) -> list[ClassifiedItem]:
    payload = [
        {"id": item.id, "title": item.title, "source": item.source, "summary": item.summary[:300]}
        for item in batch
    ]
    text = client.complete(
        system=SYSTEM_PROMPT, user_content=json.dumps(payload), max_tokens=2048, model=model
    )
    decisions = {d["id"]: d for d in _extract_json_array(text)}

    results: list[ClassifiedItem] = []
    for item in batch:
        decision = decisions.get(item.id, {})
        topic = decision.get("topic", "")
        if topic not in VALID_TOPICS:
            topic = item.category if item.category in VALID_TOPICS else "ecosystem"
        results.append(
            ClassifiedItem(
                **item.model_dump(),
                is_relevant=bool(decision.get("is_relevant", False)),
                topic=topic,
            )
        )
    return results


def _extract_json_array(text: str) -> list[dict]:
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        log.warning("classify: could not parse JSON from model response")
        return []
