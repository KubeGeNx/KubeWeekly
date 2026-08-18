from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from kubeweekly.models import RawItem
from kubeweekly.sources.base import DEFAULT_TIMEOUT, USER_AGENT

log = logging.getLogger(__name__)

API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"

# NVD rate-limits unauthenticated callers to 5 requests / 30s; space our
# per-keyword requests out to stay well under that. Set NVD_API_KEY to raise
# the limit (50 req/30s) and fetch faster.
UNAUTH_REQUEST_GAP_SECONDS = 6.5


class CveSource:
    """Recently published CVEs matching Kubernetes-ecosystem keywords, via
    the NVD CVE API keyword search.
    """

    name = "cve"

    def __init__(self, keywords: list[str], lookback_days: int = 3):
        self.keywords = keywords
        self.lookback_days = lookback_days
        self.api_key = os.environ.get("NVD_API_KEY")

    async def fetch(self, client: httpx.AsyncClient) -> list[RawItem]:
        items: list[RawItem] = []
        seen_ids: set[str] = set()
        for i, keyword in enumerate(self.keywords):
            if i > 0 and not self.api_key:
                await asyncio.sleep(UNAUTH_REQUEST_GAP_SECONDS)
            try:
                for item in await self._fetch_one(client, keyword):
                    if item.id not in seen_ids:
                        seen_ids.add(item.id)
                        items.append(item)
            except Exception:
                log.warning("cve: keyword %r failed", keyword, exc_info=True)
        return items

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
    async def _fetch_one(self, client: httpx.AsyncClient, keyword: str) -> list[RawItem]:
        since = datetime.now(timezone.utc) - timedelta(days=self.lookback_days)
        headers = {"User-Agent": USER_AGENT}
        if self.api_key:
            headers["apiKey"] = self.api_key
        resp = await client.get(
            API_URL,
            params={
                "keywordSearch": keyword,
                "pubStartDate": since.strftime("%Y-%m-%dT%H:%M:%S.000"),
                "pubEndDate": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000"),
                "resultsPerPage": 20,
            },
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        items: list[RawItem] = []
        for vuln in resp.json().get("vulnerabilities", []):
            cve = vuln.get("cve", {})
            cve_id = cve.get("id")
            if not cve_id:
                continue
            description = next(
                (d["value"] for d in cve.get("descriptions", []) if d.get("lang") == "en"), ""
            )
            severity = _extract_severity(cve.get("metrics", {}))
            items.append(
                RawItem(
                    source="nvd-cve",
                    category="security",
                    title=f"{cve_id}{f' ({severity})' if severity else ''}: {keyword}",
                    url=f"https://nvd.nist.gov/vuln/detail/{cve_id}",
                    published_at=_parse_nvd_datetime(cve["published"]),
                    summary=description[:1000],
                    meta={"cve_id": cve_id, "severity": severity, "keyword": keyword},
                )
            )
        return items


def _parse_nvd_datetime(value: str) -> datetime:
    """NVD's `published` field has no UTC offset (e.g. "2026-08-15T10:00:00.000"),
    which datetime.fromisoformat parses as naive - normalize to aware UTC so
    it can be sorted/compared against the timezone-aware datetimes every
    other connector produces.
    """
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _extract_severity(metrics: dict) -> str:
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        entries = metrics.get(key)
        if entries:
            return entries[0].get("cvssData", {}).get("baseSeverity", "")
    return ""
