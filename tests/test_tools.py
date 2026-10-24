from app.qloo import MockQloo
from app.tools import TOOL_DEFS, ToolRunner, age_band, reminiscence_window, uk_location


def test_reminiscence_and_age_band():
    assert reminiscence_window(1941) == (1949, 1973)
    assert age_band(1941) == "55_and_older"
    assert age_band(1980) == "36_to_55"
    assert age_band(None) == "55_and_older"


def test_tool_schemas_are_strict_objects():
    names = {t["name"] for t in TOOL_DEFS}
    assert {"search_entities", "taste_recommendations", "find_outing_places", "group_common_ground", "submit_plan"} <= names
    for t in TOOL_DEFS:
        assert t["input_schema"]["type"] == "object"
        assert t["input_schema"]["additionalProperties"] is False


async def test_taste_recommendations_sets_era_and_demographics():
    q = MockQloo()
    tr = ToolRunner(q)
    s = await tr.run("search_entities", {"queries": [{"name": "Elvis Presley", "type": "artist"}]})
    elvis = s["results"][0]["best"]["entity_id"]
    out = await tr.run("taste_recommendations", {"seed_entity_ids": [elvis], "type": "movie", "birth_year": 1941})
    path, params = q.calls[-1]
    assert path == "/v2/insights"
    assert params["filter.type"] == "urn:entity:movie"
    assert params["filter.release_year.min"] == 1949 and params["filter.release_year.max"] == 1973
    assert params["signal.demographics.age"] == "55_and_older"
    assert params["feature.explainability"] == "true"
    assert out["reminiscence_window"] == [1949, 1973]
    assert out["results"] and all(1949 <= r["release_year"] <= 1973 for r in out["results"])
    assert all(r["because_of"][0]["entity_id"] == elvis for r in out["results"])


async def test_books_use_publication_year_and_artists_no_era():
    q = MockQloo()
    tr = ToolRunner(q)
    await tr.run("taste_recommendations", {"seed_entity_ids": ["x"], "type": "book", "birth_year": 1950})
    assert "filter.publication_year.min" in q.calls[-1][1]
    await tr.run("taste_recommendations", {"seed_entity_ids": ["x"], "type": "artist", "birth_year": 1950})
    assert not any(k.startswith("filter.release_year") for k in q.calls[-1][1])


async def test_places_use_location_query():
    q = MockQloo()
    tr = ToolRunner(q)
    out = await tr.run("find_outing_places", {"seed_entity_ids": ["x"], "location": "Hove"})
    assert q.calls[-1][1]["filter.location.query"] == "Hove, United Kingdom"
    assert q.calls[-1][1]["filter.type"] == "urn:entity:place"
    assert out["results"] and "Hove" in out["results"][0]["address"]


async def test_group_common_ground_ranks_by_floor():
    q = MockQloo()
    tr = ToolRunner(q)
    s = await tr.run("search_entities", {"queries": [
        {"name": "Elvis Presley", "type": "artist"}, {"name": "Nat King Cole", "type": "artist"},
        {"name": "Frank Sinatra", "type": "artist"}, {"name": "Cliff Richard", "type": "artist"}]})
    ids = [r["best"]["entity_id"] for r in s["results"]]
    out = await tr.run("group_common_ground", {"type": "artist", "candidate_entity_ids": ids[2:], "residents": [
        {"name": "A", "seed_entity_ids": [ids[0]]}, {"name": "B", "seed_entity_ids": [ids[1]]}]})
    ranked = out["ranked"]
    assert len(ranked) == 2
    assert ranked[0]["group_floor"] >= ranked[1]["group_floor"]
    assert set(ranked[0]["per_resident"]) == {"A", "B"}
    assert all(c[1].get("filter.results.entities") == ids[2:] for c in q.calls[-2:])


async def test_submit_plan_flags_ungrounded_and_errors_are_returned():
    tr = ToolRunner(MockQloo())
    res = await tr.run("submit_plan", {"title": "t", "summary": "s", "conversation_prompts": [], "facilitator_tips": [], "cautions": [],
                                       "sections": [{"kind": "music", "title": "x", "items": [{"name": "Made up", "entity_id": "nope", "why": "w"}]}]})
    assert res["ungrounded_items"] == ["Made up"]
    assert "error" in await tr.run("taste_recommendations", {"seed_entity_ids": [], "type": "music"})
    assert "error" in await tr.run("does_not_exist", {})


def test_uk_location_adds_country_only_when_missing():
    assert uk_location("Brighton") == "Brighton, United Kingdom"
    assert uk_location(" Kingston upon Thames ") == "Kingston upon Thames, United Kingdom"
    assert uk_location("Brighton, CO") == "Brighton, CO"
