from app.qloo import MockQloo
from app.tools import (
    DEFAULT_OUTING_TAGS,
    OUTING_EXCLUDE_TAGS,
    TOOL_DEFS,
    ToolRunner,
    age_band,
    diversify,
    reminiscence_window,
    uk_location,
)


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


async def test_places_default_to_older_friendly_categories():
    q = MockQloo()
    tr = ToolRunner(q)
    out = await tr.run("find_outing_places", {"seed_entity_ids": ["x"], "location": "Brighton", "take": 6})
    params = q.calls[0][1]
    assert params["filter.tags"] == DEFAULT_OUTING_TAGS
    assert "urn:tag:category:place:tea_house" in params["filter.tags"]
    assert {"urn:tag:category:place:bar", "urn:tag:category:place:night_club", "urn:tag:category:place:pub"} <= set(params["filter.exclude.tags"])
    names = {r["name"] for r in out["results"]}
    assert names and not names & {"The Seven Stars", "Club Neon", "Caribbean Kitchen"}
    assert all(r.get("kind") for r in out["results"])
    kinds = [r["kind"] for r in out["results"][:3]]
    assert len(set(kinds)) == 3  # diversified: three different kinds of outing up front


async def test_places_tag_override_keeps_safety_exclusions():
    q = MockQloo()
    tr = ToolRunner(q)
    caribbean = "urn:tag:category:place:caribbean_restaurant"
    out = await tr.run("find_outing_places", {"seed_entity_ids": ["x"], "location": "Brighton", "tag_ids": [caribbean],
                                              "exclude_tag_ids": ["urn:tag:category:place:live_music_venue"], "take": 1})
    params = q.calls[0][1]
    assert params["filter.tags"] == [caribbean]
    assert set(OUTING_EXCLUDE_TAGS) <= set(params["filter.exclude.tags"])
    assert "urn:tag:category:place:live_music_venue" in params["filter.exclude.tags"]
    assert [r["name"] for r in out["results"]] == ["Caribbean Kitchen"]


class SparseQloo(MockQloo):
    """Like live Qloo in smaller towns: the taste-signalled query returns almost nothing."""

    async def insights(self, params):
        items = await super().insights(params)
        return items[:1] if "signal.interests.entities" in params else items


async def test_places_top_up_when_taste_results_are_thin():
    q = SparseQloo()
    tr = ToolRunner(q)
    out = await tr.run("find_outing_places", {"seed_entity_ids": ["x"], "location": "Kingston upon Thames", "take": 4})
    assert len(q.calls) == 2 and "signal.interests.entities" not in q.calls[1][1]
    assert q.calls[1][1]["filter.tags"] == DEFAULT_OUTING_TAGS  # top-up stays within safe categories
    matches = [r["match"] for r in out["results"]]
    assert len(out["results"]) == 4 and matches.count("taste") == 1 and matches.count("popular locally") == 3
    assert len({r["entity_id"] for r in out["results"]}) == 4


def test_diversify_keeps_order_within_kinds():
    items = [{"n": 1, "kind": "tea room"}, {"n": 2, "kind": "tea room"}, {"n": 3, "kind": "park or garden"}, {"n": 4, "kind": "museum"}]
    assert [i["n"] for i in diversify(items)] == [1, 3, 4, 2]


async def test_search_tags_can_restrict_to_place_categories():
    q = MockQloo()
    out = await ToolRunner(q).run("search_tags", {"query": "tea", "places_only": True})
    assert q.calls[-1][1]["filter.tag.types"] == "urn:tag:category:place"
    assert out["tags"] and all(t["type"] == "urn:tag:category:place" for t in out["tags"])


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


async def test_one_failed_search_does_not_sink_the_batch():
    from app.qloo import QlooError

    class Flaky(MockQloo):
        async def search(self, query, kind=None, take=5):
            if query == "Mohammed Rafi":
                raise QlooError("Qloo /search returned 429")
            return await super().search(query, kind, take)

    out = await ToolRunner(Flaky()).run("search_entities", {"queries": [
        {"name": "Lata Mangeshkar", "type": "artist"}, {"name": "Mohammed Rafi", "type": "artist"}]})
    assert out["results"][0]["best"]["name"] == "Lata Mangeshkar"
    assert out["results"][1]["best"] is None and "429" in out["results"][1]["error"]
