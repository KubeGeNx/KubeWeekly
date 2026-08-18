from __future__ import annotations

import httpx

from kubeweekly.models import RawItem
from kubeweekly.sources.rss import RssSource


class CloudProviderSource:
    """AWS/GCP/Azure 'what's new' feeds, filtered to Kubernetes-relevant
    keywords (these feeds cover far more than K8s, so most entries are noise).
    """

    name = "cloud_providers"

    def __init__(self, feeds: list[dict]):
        self.feeds = feeds
        self._rss = RssSource([{"url": f["url"], "category": f.get("category", "cloud"), "name": f["name"]} for f in feeds])
        self._keywords_by_feed = {f["name"]: [kw.lower() for kw in f.get("keywords", [])] for f in feeds}

    async def fetch(self, client: httpx.AsyncClient) -> list[RawItem]:
        all_items = await self._rss.fetch(client)
        filtered: list[RawItem] = []
        for item in all_items:
            keywords = self._keywords_by_feed.get(item.source, [])
            haystack = f"{item.title} {item.summary}".lower()
            if not keywords or any(kw in haystack for kw in keywords):
                filtered.append(item)
        return filtered
