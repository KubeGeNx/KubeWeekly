from __future__ import annotations

from typing import Protocol

import httpx

from kubeweekly.models import RawItem


class Source(Protocol):
    """A connector that fetches RawItems from one external system.

    Implementations must not raise on partial failure (a single bad feed URL,
    a timeout, a malformed entry) — log/skip and return whatever succeeded, so
    one broken source never aborts the whole ingestion run.
    """

    name: str

    async def fetch(self, client: httpx.AsyncClient) -> list[RawItem]: ...


DEFAULT_TIMEOUT = httpx.Timeout(15.0, connect=10.0)
USER_AGENT = "KubeWeekly/1.0 (+https://github.com/KubeGeNx/KubeWeekly)"
