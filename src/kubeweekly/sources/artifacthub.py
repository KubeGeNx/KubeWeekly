from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from kubeweekly.models import RawItem
from kubeweekly.sources.base import DEFAULT_TIMEOUT, USER_AGENT

log = logging.getLogger(__name__)

API_URL = "https://artifacthub.io/api/v1/packages/search"

# https://artifacthub.io/docs/api - package "kind" enum
KIND_IDS = {"helm": 0, "olm": 3}
KIND_NAMES = {v: k for k, v in KIND_IDS.items()}


class ArtifactHubSource:
    """New/updated Helm charts and OLM operators via the Artifact Hub search API."""

    name = "artifacthub"

    def __init__(self, kinds: list[str]):
        self.kinds = [KIND_IDS[k] for k in kinds if k in KIND_IDS]

    async def fetch(self, client: httpx.AsyncClient) -> list[RawItem]:
        if not self.kinds:
            return []
        try:
            return await self._fetch(client)
        except Exception:
            log.warning("artifacthub: fetch failed", exc_info=True)
            return []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def _fetch(self, client: httpx.AsyncClient) -> list[RawItem]:
        params = [("kind", k) for k in self.kinds]
        params += [("sort", "relevance"), ("limit", "30"), ("facets", "false")]
        resp = await client.get(
            API_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=DEFAULT_TIMEOUT
        )
        resp.raise_for_status()
        packages = resp.json().get("packages", [])

        items: list[RawItem] = []
        for pkg in packages:
            ts = pkg.get("ts")
            published_at = (
                datetime.fromtimestamp(ts, tz=timezone.utc) if ts else datetime.now(timezone.utc)
            )
            repo = pkg.get("repository", {})
            name = pkg.get("display_name") or pkg.get("name")
            kind_name = KIND_NAMES.get(repo.get("kind"), "helm")
            url = f"https://artifacthub.io/packages/{kind_name}/{repo.get('name', '')}/{pkg.get('name', '')}"
            items.append(
                RawItem(
                    source="artifacthub",
                    category="ecosystem",
                    title=f"{name} ({repo.get('name', 'unknown repo')}) v{pkg.get('version', '')}",
                    url=url,
                    published_at=published_at,
                    summary=pkg.get("description") or "",
                    meta={"repo": repo.get("name"), "kind": repo.get("kind")},
                )
            )
        return items
