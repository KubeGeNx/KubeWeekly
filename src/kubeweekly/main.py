from __future__ import annotations

import argparse
import asyncio
import copy
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from kubeweekly.briefing.compose import build_briefing, compose_linkedin_draft
from kubeweekly.briefing.render import enforce_linkedin_limit, write_draft
from kubeweekly.config import AppConfig, SourcesConfig
from kubeweekly.db import Database
from kubeweekly.llm import build_llm_client
from kubeweekly.pipeline.classify import classify_items
from kubeweekly.pipeline.dedup import cluster_stories
from kubeweekly.pipeline.ingest import ingest
from kubeweekly.pipeline.score import score_stories
from kubeweekly.pipeline.summarize import select_top_stories, summarize_stories
from kubeweekly.pipeline.trends import detect_trends
from kubeweekly.sources import build_sources

log = logging.getLogger(__name__)

RELEVANT_LOOKBACK = timedelta(days=1)


def reduce_for_dry_run(sources_config: SourcesConfig) -> SourcesConfig:
    """Small, fast subset for --dry-run: a couple of RSS feeds + HN only."""
    reduced = copy.deepcopy(sources_config)
    reduced.rss = reduced.rss[:2]
    reduced.hackernews = {"enabled": True, "queries": ["kubernetes"]} if reduced.hackernews.get("enabled") else {}
    reduced.github = {}
    reduced.artifacthub = {}
    reduced.reddit = {}
    reduced.cve = {}
    reduced.cloud_providers = []
    reduced.mailing_lists = []
    return reduced


def run(config: AppConfig) -> None:
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")

    sources_config = SourcesConfig.load(config.sources_path)
    if config.dry_run:
        sources_config = reduce_for_dry_run(sources_config)

    db_path = ":memory:" if config.dry_run else config.db_path
    db = Database(db_path)
    llm_client = build_llm_client(config.llm_provider, config.llm_api_key)
    log.info("run: using LLM_PROVIDER=%s (classify/score=%s, summarize/compose=%s)",
             config.llm_provider, config.classify_model, config.summarize_model)

    try:
        sources = build_sources(sources_config, github_token=config.github_token)
        new_count = asyncio.run(ingest(sources, db))
        log.info("run: ingested %d new items", new_count)

        unclassified = db.unclassified_items()
        classified = classify_items(llm_client, unclassified, config.classify_model)
        for item in classified:
            db.mark_classified(item)
        log.info("run: classified %d items (%d relevant)", len(classified), sum(i.is_relevant for i in classified))

        relevant_items = db.relevant_items_since(now - RELEVANT_LOOKBACK)
        stories = cluster_stories(relevant_items)
        stories = score_stories(llm_client, stories, config.classify_model)
        log.info("run: clustered into %d stories", len(stories))

        trend_signals, what_changed = detect_trends(stories, db, now)

        top_stories = select_top_stories(stories)
        summarize_stories(llm_client, top_stories, config.summarize_model)

        briefing = build_briefing(date_str, stories, top_stories, trend_signals, what_changed)
        linkedin_text = compose_linkedin_draft(llm_client, briefing, config.summarize_model)
        briefing.linkedin_text = enforce_linkedin_limit(linkedin_text)

        if config.dry_run:
            print("\n" + "=" * 60)
            print(briefing.linkedin_text)
            print("=" * 60 + "\n")
        else:
            path = write_draft(config.output_dir, briefing)
            db.save_stories(stories, date_str)
            db.save_briefing(date_str, briefing.linkedin_text, briefing.category_counts)
            log.info("run: draft written to %s", path)
    finally:
        db.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="KubeWeekly: Kubernetes intelligence briefing pipeline")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run against a small source subset, print the draft, skip DB persistence",
    )
    args = parser.parse_args()

    # Deliberately outside the repo (~/.env, not ./.env) so secrets can never
    # land in this git tree even by accident. No-op if the file is absent.
    load_dotenv(Path.home() / ".env")
    config = AppConfig.from_env(dry_run=args.dry_run)
    run(config)


if __name__ == "__main__":
    main()
