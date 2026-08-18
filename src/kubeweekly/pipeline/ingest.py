from __future__ import annotations

import asyncio
import logging

import httpx

from kubeweekly.db import Database
from kubeweekly.models import RawItem, utcnow
from kubeweekly.sources.base import Source

log = logging.getLogger(__name__)


async def ingest(sources: list[Source], db: Database) -> int:
    """Fetches from every connector concurrently and upserts new items.

    Returns the count of newly inserted items. A connector raising is caught
    here too, as a last line of defense, so one bad source never aborts the
    run for the rest.
    """
    async with httpx.AsyncClient(follow_redirects=True) as client:
        results = await asyncio.gather(
            *(_fetch_safely(source, client) for source in sources), return_exceptions=False
        )

    all_items: list[RawItem] = [item for batch in results for item in batch]

    now = utcnow()
    new_count = 0
    for item in all_items:
        if db.upsert_raw_item(item, now):
            new_count += 1

    log.info("ingest: %d items fetched, %d new", len(all_items), new_count)
    return new_count


async def _fetch_safely(source: Source, client: httpx.AsyncClient) -> list[RawItem]:
    try:
        return await source.fetch(client)
    except Exception:
        log.warning("ingest: source %s raised, skipping", getattr(source, "name", source), exc_info=True)
        return []
