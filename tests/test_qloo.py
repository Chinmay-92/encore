import httpx
import pytest

from app.qloo import HACKATHON_BASE_URL, MockQloo, QlooClient, QlooError, build_qloo, slim_entity, to_urn

INSIGHTS_BODY = {
    "success": True,
    "results": {
        "entities": [
            {
                "entity_id": "E1",
                "name": "Mary Poppins",
                "types": ["urn:entity:movie"],
                "popularity": 0.9612,
                "properties": {"release_year": 1964, "image": {"url": "https://img/x.jpg"}, "akas": [{"value": "x"}]},
                "query": {"affinity": 0.8771, "explainability": {"signal.interests.entities": [{"entity_id": "S1", "score": 0.91}]}},
                "tags": [{"id": "urn:tag:genre:musical", "name": "Musical"}],
            }
        ]
    },
}


def make_client(handler):
    return QlooClient("test-key", transport=httpx.MockTransport(handler), retry_delay=0)


async def test_insights_request_shape_and_parsing():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = request.url
        seen["key"] = request.headers.get("x-api-key")
        return httpx.Response(200, json=INSIGHTS_BODY)

    c = make_client(handler)
    out = await c.insights({"filter.type": "urn:entity:movie", "signal.interests.entities": ["S1", "S2"], "take": 5, "unused": None})
    assert seen["key"] == "test-key"
    assert seen["url"].host == "hackathon.api.qloo.com"
    assert seen["url"].path == "/v2/insights"
    assert seen["url"].params["signal.interests.entities"] == "S1,S2"
    assert "unused" not in seen["url"].params
    assert out == [
        {
            "entity_id": "E1", "name": "Mary Poppins", "type": "urn:entity:movie", "release_year": 1964,
            "image": "https://img/x.jpg", "popularity": 0.961, "affinity": 0.877,
            "because_of": [{"entity_id": "S1", "score": 0.91}], "tags": ["Musical"],
        }
    ]
    await c.aclose()


async def test_search_uses_types_and_caches():
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(200, json={"results": [{"entity_id": "A1", "name": "Elvis Presley", "types": ["urn:entity:artist"]}]})

    c = make_client(handler)
    a = await c.search("Elvis", "artist")
    b = await c.search("Elvis", "artist")
    assert a == b and a[0]["name"] == "Elvis Presley"
    assert len(calls) == 1
    assert calls[0].path == "/search" and calls[0].params["types"] == "urn:entity:artist"


async def test_404_is_empty_and_500_raises():
    c404 = make_client(lambda r: httpx.Response(404, json={"code": 404}))
    assert await c404.insights({"filter.type": "urn:entity:movie"}) == []
    c500 = make_client(lambda r: httpx.Response(500, text="boom"))
    with pytest.raises(QlooError):
        await c500.insights({"filter.type": "urn:entity:movie"})


async def test_429_retried_once():
    n = {"i": 0}

    def handler(r):
        n["i"] += 1
        return httpx.Response(429) if n["i"] == 1 else httpx.Response(200, json=INSIGHTS_BODY)

    out = await make_client(handler).insights({"filter.type": "urn:entity:movie"})
    assert n["i"] == 2 and out[0]["name"] == "Mary Poppins"


def test_to_urn_and_factory():
    assert to_urn("tv_show") == "urn:entity:tv_show"
    with pytest.raises(QlooError):
        to_urn("music")
    assert isinstance(build_qloo(None), MockQloo)
    assert isinstance(build_qloo("k"), QlooClient)
    assert HACKATHON_BASE_URL == "https://hackathon.api.qloo.com"


def test_slim_entity_drops_noise():
    e = slim_entity({"entity_id": "x", "name": "n", "properties": {"akas": [1, 2]}})
    assert "akas" not in e


def test_slim_place_surfaces_category_tags_and_accessibility():
    e = slim_entity({
        "entity_id": "P1", "name": "Stanmer Tea Rooms", "types": ["urn:entity:place"],
        "tags": [
            {"id": "urn:tag:credit_card:place:mastercard", "name": "Mastercard"},
            {"id": "urn:tag:accessibility:place:wheelchair_accessible_entrance", "name": "Wheelchair accessible entrance"},
            {"id": "urn:tag:genre:place:tourist_attraction", "name": "Tourist attraction"},
            {"id": "urn:tag:category:place:tea_house", "name": "Tea house"},
            {"id": "urn:tag:genre:place:tea_house", "name": "Tea house"},
            {"id": "urn:tag:category:place:place", "name": "Place"},
        ],
    })
    assert e["tags"] == ["Tea house", "Tourist attraction", "Mastercard", "Wheelchair accessible entrance"]
    assert e["wheelchair_accessible"] is True
