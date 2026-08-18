from __future__ import annotations

import httpx
import respx

from kubeweekly.sources.cve import CveSource


@respx.mock
async def test_cve_source_produces_timezone_aware_datetimes():
    """NVD's `published` field has no UTC offset - regression test for a bug
    where this produced naive datetimes that crashed sorting against the
    timezone-aware datetimes every other connector produces.
    """
    respx.get("https://services.nvd.nist.gov/rest/json/cves/2.0").mock(
        return_value=httpx.Response(
            200,
            json={
                "vulnerabilities": [
                    {
                        "cve": {
                            "id": "CVE-2026-12345",
                            "published": "2026-08-15T10:00:00.000",
                            "descriptions": [{"lang": "en", "value": "A test CVE"}],
                            "metrics": {
                                "cvssMetricV31": [{"cvssData": {"baseSeverity": "HIGH"}}]
                            },
                        }
                    }
                ]
            },
        )
    )

    source = CveSource(keywords=["kubernetes"])
    async with httpx.AsyncClient() as client:
        items = await source.fetch(client)

    assert len(items) == 1
    assert items[0].published_at.tzinfo is not None
    assert items[0].meta["severity"] == "HIGH"
