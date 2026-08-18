from __future__ import annotations

import httpx
import respx

from kubeweekly.sources.hackernews import HackerNewsSource


@respx.mock
async def test_hackernews_source_normalizes_hits():
    respx.get("https://hn.algolia.com/api/v1/search_by_date").mock(
        return_value=httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "title": "Kubernetes 1.34 released",
                        "url": "https://kubernetes.io/blog/1-34",
                        "created_at_i": 1755250000,
                        "points": 120,
                        "num_comments": 40,
                        "objectID": "123",
                    },
                    {
                        "title": "Ask HN: best k8s operator patterns?",
                        "url": None,
                        "created_at_i": 1755250100,
                        "points": 10,
                        "num_comments": 5,
                        "objectID": "456",
                    },
                ]
            },
        )
    )

    source = HackerNewsSource(queries=["kubernetes"])
    async with httpx.AsyncClient() as client:
        items = await source.fetch(client)

    assert len(items) == 2
    assert items[0].url == "https://kubernetes.io/blog/1-34"
    assert items[1].url == "https://news.ycombinator.com/item?id=456"
    assert items[0].meta["points"] == 120


@respx.mock
async def test_hackernews_deduplicates_across_queries():
    hit = {
        "title": "Kubernetes news",
        "url": "https://example.com/a",
        "created_at_i": 1755250000,
        "points": 1,
        "num_comments": 0,
        "objectID": "1",
    }
    respx.get("https://hn.algolia.com/api/v1/search_by_date").mock(
        return_value=httpx.Response(200, json={"hits": [hit]})
    )

    source = HackerNewsSource(queries=["kubernetes", "k8s"])
    async with httpx.AsyncClient() as client:
        items = await source.fetch(client)

    assert len(items) == 1
