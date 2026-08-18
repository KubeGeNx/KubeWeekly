from __future__ import annotations

import hashlib
import re
from collections import Counter
from difflib import SequenceMatcher

from kubeweekly.models import ClassifiedItem, Story

# Title-similarity clustering is a deliberately simple heuristic rather than
# an LLM call: dedup at this volume is mostly near-identical titles (the same
# release/CVE covered by several blogs), where string similarity is cheap and
# reliable. Revisit with embeddings only if false-splits become a problem.
SIMILARITY_THRESHOLD = 0.62

_WORD_RE = re.compile(r"[a-z0-9]+")


def cluster_stories(items: list[ClassifiedItem]) -> list[Story]:
    relevant = [i for i in items if i.is_relevant]
    relevant.sort(key=lambda i: i.published_at)

    clusters: list[list[ClassifiedItem]] = []
    normalized_titles: list[str] = []

    for item in relevant:
        norm = _normalize(item.title)
        match_idx = None
        for idx, existing_norm in enumerate(normalized_titles):
            if SequenceMatcher(None, norm, existing_norm).ratio() >= SIMILARITY_THRESHOLD:
                match_idx = idx
                break
        if match_idx is None:
            clusters.append([item])
            normalized_titles.append(norm)
        else:
            clusters[match_idx].append(item)

    return [_build_story(cluster) for cluster in clusters]


def _normalize(title: str) -> str:
    return " ".join(sorted(_WORD_RE.findall(title.lower())))


def _build_story(cluster: list[ClassifiedItem]) -> Story:
    canonical = min(cluster, key=lambda i: i.published_at)
    topic = Counter(i.topic for i in cluster).most_common(1)[0][0]
    story_id = hashlib.sha256(canonical.url.encode()).hexdigest()[:16]
    return Story(
        id=story_id,
        canonical_url=canonical.url,
        title=canonical.title,
        topic=topic,
        items=cluster,
        published_at=canonical.published_at,
    )
