from __future__ import annotations

import logging
from datetime import datetime, timezone

import feedparser
import httpx

from kubeweekly.models import RawItem
from kubeweekly.sources.base import DEFAULT_TIMEOUT, USER_AGENT

log = logging.getLogger(__name__)


class MailingListSource:
    """Best-effort connector for Kubernetes SIG mailing lists.

    Most SIG discussion lives on Google Groups, which does not expose a
    reliable public RSS feed on its current UI. This connector tries the
    legacy `forum/feed/<group>/msgs/rss_v2_0.xml` path, which still works for
    some groups but not all. Treat this source as low-confidence: it is
    expected to return nothing for groups that have no working feed, and that
    must never fail the overall ingestion run.
    """

    name = "mailing_lists"

    def __init__(self, groups: list[dict]):
        self.groups = groups

    async def fetch(self, client: httpx.AsyncClient) -> list[RawItem]:
        items: list[RawItem] = []
        for group_cfg in self.groups:
            try:
                items.extend(await self._fetch_one(client, group_cfg))
            except Exception:
                log.info(
                    "mailing_lists: no usable feed for %s (expected for most groups)",
                    group_cfg.get("name"),
                )
        return items

    async def _fetch_one(self, client: httpx.AsyncClient, group_cfg: dict) -> list[RawItem]:
        name = group_cfg["name"]
        category = group_cfg.get("category", "core")
        feed_url = f"https://groups.google.com/forum/feed/{name}/msgs/rss_v2_0.xml"

        resp = await client.get(feed_url, headers={"User-Agent": USER_AGENT}, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        if parsed.bozo and not parsed.entries:
            return []

        items: list[RawItem] = []
        for entry in parsed.entries:
            link = entry.get("link")
            title = entry.get("title")
            if not link or not title:
                continue
            published = entry.get("published_parsed")
            items.append(
                RawItem(
                    source=f"mailing-list/{name}",
                    category=category,
                    title=title,
                    url=link,
                    published_at=datetime(*published[:6], tzinfo=timezone.utc)
                    if published
                    else datetime.now(timezone.utc),
                    summary=entry.get("summary", "")[:1000],
                    meta={"group": name},
                )
            )
        return items
