from __future__ import annotations

import json
import logging
from collections import Counter

from kubeweekly.llm import LLMClient
from kubeweekly.models import Briefing, Story, TrendSignal

log = logging.getLogger(__name__)

TOP_HEADLINE_COUNT = 3

SYSTEM_PROMPT = """You write the "Kubernetes Daily" LinkedIn post: a daily
intelligence briefing on Kubernetes/CNCF ecosystem news for platform
engineers, SREs, and infra leads.

Ground every claim in the structured data you're given - never invent
stories, numbers, or facts not present in the input.

Write like an experienced engineer sharing genuine takes with peers, not a
report template with fields filled in. That means:
- No literal section labels like "Signal vs. noise:", "What changed since
  yesterday:", or "Watch tomorrow:" - fold that reasoning into normal
  sentences instead.
- No pipe-delimited or colon-delimited stat lines (e.g. "Security: 1 |
  Ecosystem: 7"). If you mention category counts at all, weave them into a
  sentence ("a dozen ecosystem releases and one CVE worth your attention").
- No markdown headers, bold/asterisks, or bullet characters other than a
  plain numbered list for the headline items.
- Every sentence should sound like it was typed by a person, not assembled
  from a fixed template - vary the phrasing run to run.

Loose shape to hit (not a fill-in-the-blanks form):

Kubernetes Daily — <date>

<one-line hook that would make someone stop scrolling, referencing the single
most important item - this is the only line before LinkedIn's "see more"
truncation, so it has to stand alone>

<a numbered list of 2-4 items, most important first, each one sentence:
what happened and why a platform engineer should care - pull these from
top_stories>

<one short paragraph (2-3 sentences) that reads as your own analysis: which
of the above actually matters most and why, how today compares to
yesterday, and anything worth watching next - grounded only in
what_changed and trend_signals, don't speculate beyond them>

<3-5 relevant hashtags>

Respect LinkedIn's ~3000 character limit - keep the whole post well under
that, ideally under 1500 characters total.

Output ONLY the post text, nothing else - no preamble, no markdown fences.
"""


def build_briefing(
    date: str,
    all_stories: list[Story],
    top_stories: list[Story],
    trend_signals: list[TrendSignal],
    what_changed: str,
) -> Briefing:
    category_counts = dict(Counter(s.topic for s in all_stories))
    headline_stories = sorted(top_stories, key=lambda s: s.score, reverse=True)[:TOP_HEADLINE_COUNT]
    return Briefing(
        date=date,
        top_stories=headline_stories,
        category_counts=category_counts,
        trend_signals=trend_signals,
        what_changed=what_changed,
        watch_tomorrow="",
    )


def compose_linkedin_draft(client: LLMClient, briefing: Briefing, model: str) -> str:
    payload = {
        "date": briefing.date,
        "top_stories": [
            {"title": s.title, "topic": s.topic, "summary": s.summary, "url": s.canonical_url}
            for s in briefing.top_stories
        ],
        "category_counts": briefing.category_counts,
        "trend_signals": [{"label": t.label, "detail": t.detail} for t in briefing.trend_signals],
        "what_changed": briefing.what_changed,
    }
    try:
        text = client.complete(
            system=SYSTEM_PROMPT, user_content=json.dumps(payload), max_tokens=1500, model=model
        )
        if text:
            return text
        log.warning("compose: model returned empty text, falling back to a plain-template draft")
    except Exception:
        log.warning("compose: LLM composition failed, falling back to a plain-template draft", exc_info=True)
    return _fallback_draft(briefing)


def _fallback_draft(briefing: Briefing) -> str:
    """Deterministic, non-LLM draft used if the compose call fails or errors
    out (e.g. API outage, no credits) - so a pipeline run still produces
    something reviewable instead of crashing with no output at all.
    """
    lines = [f"Kubernetes Daily — {briefing.date}", ""]
    for i, story in enumerate(briefing.top_stories, 1):
        lines.append(f"{i}. {story.title}")
    lines.append("")
    for topic, count in sorted(briefing.category_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"{topic}: {count}")
    lines.append("")
    lines.append(f"What changed since yesterday: {briefing.what_changed}")
    if briefing.trend_signals:
        lines.append("")
        for signal in briefing.trend_signals:
            lines.append(f"{signal.label}: {signal.detail}")
    return "\n".join(lines)
