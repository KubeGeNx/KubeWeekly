from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from kubeweekly.models import RawItem
from kubeweekly.sources.base import DEFAULT_TIMEOUT, USER_AGENT

log = logging.getLogger(__name__)

API_BASE = "https://api.github.com"


class GitHubSource:
    """Release activity for curated repos, plus topic-search for unusually
    active repos in the ecosystem (used for the 'GitHub' watch-list section).
    """

    name = "github"

    def __init__(self, releases: list[str], topic_search: dict, token: str | None = None):
        self.releases = releases
        self.topic_search = topic_search
        self.token = token

    def _headers(self) -> dict:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": USER_AGENT,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def fetch(self, client: httpx.AsyncClient) -> list[RawItem]:
        items: list[RawItem] = []
        for repo in self.releases:
            try:
                items.extend(await self._fetch_releases(client, repo))
            except Exception:
                log.warning("github: failed to fetch releases for %s", repo, exc_info=True)
        if self.topic_search.get("topic"):
            try:
                items.extend(await self._fetch_topic_search(client))
            except Exception:
                log.warning("github: topic search failed", exc_info=True)
        return items

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def _fetch_releases(self, client: httpx.AsyncClient, repo: str) -> list[RawItem]:
        resp = await client.get(
            f"{API_BASE}/repos/{repo}/releases",
            params={"per_page": 5},
            headers=self._headers(),
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        items: list[RawItem] = []
        for rel in resp.json():
            if rel.get("draft"):
                continue
            published = rel.get("published_at") or rel.get("created_at")
            if not published:
                continue
            items.append(
                RawItem(
                    source=f"github/{repo}",
                    category="core" if repo.startswith("kubernetes/") else "ecosystem",
                    title=f"{repo} {rel.get('tag_name', '')}: {rel.get('name') or rel.get('tag_name')}",
                    url=rel["html_url"],
                    published_at=datetime.fromisoformat(published.replace("Z", "+00:00")),
                    summary=(rel.get("body") or "")[:2000],
                    meta={"repo": repo, "tag": rel.get("tag_name")},
                )
            )
        return items

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def _fetch_topic_search(self, client: httpx.AsyncClient) -> list[RawItem]:
        topic = self.topic_search["topic"]
        min_stars = self.topic_search.get("min_stars", 50)
        since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        query = f"topic:{topic} pushed:>{since} stars:>={min_stars}"
        resp = await client.get(
            f"{API_BASE}/search/repositories",
            params={"q": query, "sort": "updated", "order": "desc", "per_page": 15},
            headers=self._headers(),
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        items: list[RawItem] = []
        for repo in resp.json().get("items", []):
            pushed_at = repo.get("pushed_at")
            if not pushed_at:
                continue
            items.append(
                RawItem(
                    source="github/topic-search",
                    category="emerging",
                    title=f"{repo['full_name']}: unusually active ({repo['stargazers_count']}★)",
                    url=repo["html_url"],
                    published_at=datetime.fromisoformat(pushed_at.replace("Z", "+00:00")),
                    summary=repo.get("description") or "",
                    meta={"stars": repo["stargazers_count"], "full_name": repo["full_name"]},
                )
            )
        return items
