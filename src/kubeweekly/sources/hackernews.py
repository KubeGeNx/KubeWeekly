from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from kubeweekly.models import RawItem
from kubeweekly.sources.base import DEFAULT_TIMEOUT, USER_AGENT

log = logging.getLogger(__name__)

API_URL = "https://hn.algolia.com/api/v1/search_by_date"


class HackerNewsSource:
    """Recent Hacker News stories matching Kubernetes-related queries."""

    name = "hackernews"

    def __init__(self, queries: list[str], lookback_days: int = 2):
        self.queries = queries
        self.lookback_days = lookback_days

    async def fetch(self, client: httpx.AsyncClient) -> list[RawItem]:
        items: list[RawItem] = []
        seen_ids: set[str] = set()
        for query in self.queries:
            try:
                for item in await self._fetch_one(client, query):
                    if item.id not in seen_ids:
                        seen_ids.add(item.id)
                        items.append(item)
            except Exception:
                log.warning("hackernews: query %r failed", query, exc_info=True)
        return items

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def _fetch_one(self, client: httpx.AsyncClient, query: str) -> list[RawItem]:
        since = int((datetime.now(timezone.utc) - timedelta(days=self.lookback_days)).timestamp())
        resp = await client.get(
            API_URL,
            params={
                "query": query,
                "tags": "story",
                "numericFilters": f"created_at_i>{since}",
                "hitsPerPage": 20,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        items: list[RawItem] = []
        for hit in resp.json().get("hits", []):
            title = hit.get("title")
            if not title:
                continue
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}"
            items.append(
                RawItem(
                    source="hackernews",
                    category="emerging",
                    title=title,
                    url=url,
                    published_at=datetime.fromtimestamp(hit["created_at_i"], tz=timezone.utc),
                    summary="",
                    meta={
                        "points": hit.get("points", 0),
                        "num_comments": hit.get("num_comments", 0),
                        "hn_id": hit["objectID"],
                        "query": query,
                    },
                )
            )
        return items
