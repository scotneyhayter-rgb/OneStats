"""Trove newspaper search (research discovery). No network or API key: the HTTP client is injected
with a recorded Trove v3 response, so parsing and the no-key behaviour are both verified offline."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from onestats.core.config import Settings
from onestats.domain.research import trove
from onestats.main import create_app

# A trimmed but shape-accurate Trove v3 /result response for the newspaper category.
SAMPLE = {
    "category": [
        {
            "code": "newspaper",
            "records": {
                "total": 2,
                "n": 2,
                "article": [
                    {
                        "id": "61812345",
                        "heading": "CRICKET. RHYMNEY v. MOYSTON.",
                        "title": {"id": "73", "value": "Ararat Advertiser (Vic. : 1857 - 1918)"},
                        "date": "1905-01-14",
                        "page": "3",
                        "snippet": "A keenly contested match was played on Saturday...",
                        "troveUrl": "https://trove.nla.gov.au/ndp/del/article/61812345",
                    },
                    {
                        "id": "61899999",
                        "heading": "DISTRICT CRICKET.",
                        "title": "Pleasant Creek News",
                        "date": "1905-02-04",
                        "snippet": "Scores: Rhymney 112, Moyston 98...",
                        "troveUrl": "https://trove.nla.gov.au/ndp/del/article/61899999",
                    },
                ],
            },
        }
    ]
}


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.last_params = None

    def result(self, params):
        self.last_params = params
        return self.payload


def test_search_parses_articles():
    fake = FakeClient(SAMPLE)
    out = trove.search_newspapers(Settings(_env_file=None), query="Rhymney cricket",
                                  year_from=1900, year_to=1909, client=fake)
    assert out["total"] == 2
    assert out["source"].startswith("Trove")
    first = out["results"][0]
    assert first["heading"].startswith("CRICKET")
    assert first["newspaper"] == "Ararat Advertiser (Vic. : 1857 - 1918)"   # nested title.value
    assert first["date"] == "1905-01-14"
    assert first["url"].endswith("/article/61812345")
    assert out["results"][1]["newspaper"] == "Pleasant Creek News"          # plain-string title
    # the 1900s decade facet was applied
    assert ("l-decade", "190") in fake.last_params
    assert ("category", "newspaper") in fake.last_params


def test_empty_query_rejected():
    with pytest.raises(trove.TroveError):
        trove.search_newspapers(Settings(_env_file=None), query="   ", client=FakeClient(SAMPLE))


def test_missing_key_reports_clearly():
    # No injected client and no configured key → a clear, non-fabricating error.
    with pytest.raises(trove.TroveError, match="Trove API key"):
        trove.search_newspapers(Settings(_env_file=None, trove_api_key=None), query="cricket")


def test_decades_in_range():
    assert trove._decades_in_range(1898, 1912) == ["189", "190", "191"]
    assert trove._decades_in_range(None, None) == []
    assert trove._decades_in_range(1905, None) == ["190"]


def test_route_registered_and_requires_auth():
    client = TestClient(create_app(Settings(env="test", db_password=None, _env_file=None)))
    assert "/api/v1/workspaces/{workspace_id}/research/newspaper-search" in client.app.openapi()["paths"]
    wid = uuid.uuid4()
    assert client.get(f"/api/v1/workspaces/{wid}/research/newspaper-search?q=cricket").status_code == 401
