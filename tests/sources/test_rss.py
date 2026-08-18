from __future__ import annotations

import httpx
import respx

from kubeweekly.sources.rss import RssSource


@respx.mock
async def test_rss_source_normalizes_entries(fixtures_dir):
    feed_xml = (fixtures_dir / "sample_feed.xml").read_bytes()
    respx.get("https://example.com/feed.xml").mock(
        return_value=httpx.Response(200, content=feed_xml)
    )

    source = RssSource([{"url": "https://example.com/feed.xml", "category": "core", "name": "Test Feed"}])
    async with httpx.AsyncClient() as client:
        items = await source.fetch(client)

    assert len(items) == 2
    assert items[0].title == "Kubernetes 1.34: New Feature Announcement"
    assert items[0].url == "https://kubernetes.io/blog/2026/08/15/k8s-1-34/"
    assert items[0].category == "core"
    assert items[0].source == "Test Feed"
    assert items[0].published_at.year == 2026


@respx.mock
async def test_rss_source_skips_broken_feed_without_raising():
    respx.get("https://example.com/broken.xml").mock(return_value=httpx.Response(500))

    source = RssSource([{"url": "https://example.com/broken.xml", "category": "core", "name": "Broken"}])
    async with httpx.AsyncClient() as client:
        items = await source.fetch(client)

    assert items == []
