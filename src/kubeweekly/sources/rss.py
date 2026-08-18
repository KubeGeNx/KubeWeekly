from __future__ import annotations

import logging
from datetime import datetime, timezone

import feedparser
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from kubeweekly.models import RawItem, utcnow
from kubeweekly.sources.base import DEFAULT_TIMEOUT, USER_AGENT

log = logging.getLogger(__name__)


class RssSource:
    """Generic RSS/Atom connector, configured with a list of feeds.

    Each feed dict: {url, category, name}.
    """

    name = "rss"

    def __init__(self, feeds: list[dict]):
        self.feeds = feeds

    async def fetch(self, client: httpx.AsyncClient) -> list[RawItem]:
        items: list[RawItem] = []
        for feed_cfg in self.feeds:
            try:
                items.extend(await self._fetch_one(client, feed_cfg))
            except Exception:
                log.warning("rss: failed to fetch %s", feed_cfg.get("url"), exc_info=True)
        return items

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def _fetch_one(self, client: httpx.AsyncClient, feed_cfg: dict) -> list[RawItem]:
        url = feed_cfg["url"]
        category = feed_cfg.get("category", "ecosystem")
        source_name = feed_cfg.get("name", url)

        resp = await client.get(url, timeout=DEFAULT_TIMEOUT, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)

        items: list[RawItem] = []
        for entry in parsed.entries:
            link = entry.get("link")
            title = entry.get("title")
            if not link or not title:
                continue
            items.append(
                RawItem(
                    source=source_name,
                    category=category,
                    title=title,
                    url=link,
                    published_at=_entry_published(entry),
                    summary=entry.get("summary", ""),
                    meta={"feed_url": url},
                )
            )
        return items


def _entry_published(entry) -> datetime:
    for field in ("published_parsed", "updated_parsed"):
        struct = entry.get(field)
        if struct:
            return datetime(*struct[:6], tzinfo=timezone.utc)
    return utcnow()
