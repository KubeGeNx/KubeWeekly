from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from kubeweekly.models import RawItem
from kubeweekly.sources.base import DEFAULT_TIMEOUT, USER_AGENT

log = logging.getLogger(__name__)


class RedditSource:
    """Recent posts from configured subreddits via the public .json listing
    endpoints.

    Reddit has been aggressively blocking unauthenticated .json requests with
    a blanket 403 regardless of User-Agent (observed from cloud/datacenter
    IPs in particular) - this connector fails gracefully in that case and
    returns an empty list rather than raising. If this becomes the norm,
    the fix is registering a Reddit OAuth app (script-type) and switching to
    the authenticated `oauth.reddit.com` API instead of the public JSON one.
    """

    name = "reddit"

    def __init__(self, subreddits: list[str]):
        self.subreddits = subreddits

    async def fetch(self, client: httpx.AsyncClient) -> list[RawItem]:
        items: list[RawItem] = []
        for sub in self.subreddits:
            try:
                items.extend(await self._fetch_one(client, sub))
            except Exception:
                log.warning("reddit: r/%s failed", sub, exc_info=True)
        return items

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def _fetch_one(self, client: httpx.AsyncClient, sub: str) -> list[RawItem]:
        resp = await client.get(
            f"https://www.reddit.com/r/{sub}/new.json",
            params={"limit": 25},
            headers={"User-Agent": USER_AGENT},
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        items: list[RawItem] = []
        for child in resp.json().get("data", {}).get("children", []):
            post = child.get("data", {})
            title = post.get("title")
            permalink = post.get("permalink")
            if not title or not permalink:
                continue
            items.append(
                RawItem(
                    source=f"reddit/r/{sub}",
                    category="emerging" if sub != "kubernetes" else "ecosystem",
                    title=title,
                    url=f"https://www.reddit.com{permalink}",
                    published_at=datetime.fromtimestamp(post["created_utc"], tz=timezone.utc),
                    summary=(post.get("selftext") or "")[:1000],
                    meta={"score": post.get("score", 0), "num_comments": post.get("num_comments", 0)},
                )
            )
        return items
