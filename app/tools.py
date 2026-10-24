"""Agent tools. Each one wraps one or more Qloo API calls."""

from __future__ import annotations

import asyncio
from typing import Any

from .qloo import QlooError, QlooLike, to_urn

ERA_TYPES = {"movie", "tv_show", "book"}


def reminiscence_window(birth_year: int) -> tuple[int, int]:
    """The 'reminiscence bump': memories from roughly ages 10-30 are the most vivid
    and best preserved in dementia, so we bias media toward that window."""
    return birth_year + 8, birth_year + 32


def age_band(birth_year: int | None, this_year: int = 2026) -> str:
    if birth_year is None:
        return "55_and_older"
    age = this_year - birth_year
    if age >= 55:
        return "55_and_older"
    if age >= 36:
        return "36_to_55"
    return "35_and_younger"


def uk_location(location: str) -> str:
    """Qloo resolves a bare 'Brighton' to Brighton, Colorado. Encore is built for UK
    care homes, so a town with no region or country gets ', United Kingdom' added."""
    location = location.strip()
    return location if "," in location else f"{location}, United Kingdom"


def _place_tags(*slugs: str) -> list[str]:
    return [f"urn:tag:category:place:{s}" for s in slugs]


# Unfiltered, Qloo's place results for a town skew to whatever its taste graph rates highly:
# in Brighton that means bars and nightspots. Outings for people living with dementia need calm,
# daytime venues, so by default we restrict to these Qloo place categories (filter.tags is OR).
OUTING_CATEGORIES: dict[str, list[str]] = {
    "tea room": _place_tags("tea_house"),
    "museum": _place_tags("museum", "art_museum", "history_museum", "local_history_museum"),
    "art gallery": _place_tags("art_gallery"),
    "park or garden": _place_tags("park", "garden", "botanical_garden"),
    "garden centre": _place_tags("garden_center"),
    "theatre": _place_tags("performing_arts_theater", "concert_hall"),
    "cinema": _place_tags("movie_theater"),
    "seafront": _place_tags("pier", "promenade"),
    "library": _place_tags("library", "public_library"),
}
DEFAULT_OUTING_TAGS = [t for tags in OUTING_CATEGORIES.values() for t in tags]
# Always excluded, even when the agent picks its own tag_ids. Coffee stands/stores drop the
# takeaway chains that Qloo also files under "tea house".
OUTING_EXCLUDE_TAGS = _place_tags(
    "bar", "pub", "night_club", "nightlife", "live_music_bar", "cocktail_bar", "wine_bar", "beer_hall",
    "casino", "comedy_club", "fast_food", "fast_food_restaurant", "hotel", "coffee_stand", "coffee_store",
)
_KIND_BY_TAG_NAME = {t.rsplit(":", 1)[-1].replace("_", " "): kind for kind, tags in OUTING_CATEGORIES.items() for t in tags}


def outing_kind(place: dict) -> str | None:
    """Which curated category a place belongs to, from its (category-first) tag names."""
    for name in place.get("tags", []):
        if kind := _KIND_BY_TAG_NAME.get(name.lower()):
            return kind
    return None


def diversify(items: list[dict], key: str = "kind") -> list[dict]:
    """Keep rank order, but let the best of each kind go first so three outing ideas aren't three tea rooms."""
    seen: set = set()
    first, rest = [], []
    for it in items:
        (rest if it.get(key) in seen else first).append(it)
        seen.add(it.get(key))
    return first + rest


def _schema(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


TOOL_DEFS: list[dict] = [
    {
        "name": "search_entities",
        "description": (
            "Resolve names of things a resident loves (singers, films, TV shows, books, places) to Qloo entity IDs. "
            "Batch every name you need in one call. Always do this before asking for recommendations."
        ),
        "input_schema": _schema(
            {
                "queries": {
                    "type": "array",
                    "items": _schema(
                        {
                            "name": {"type": "string"},
                            "type": {"type": "string", "enum": ["artist", "movie", "tv_show", "book", "place"]},
                        },
                        ["name", "type"],
                    ),
                }
            },
            ["queries"],
        ),
    },
    {
        "name": "taste_recommendations",
        "description": (
            "Ask Qloo's taste graph for entities of one type that people who love the seed entities also love. "
            "Cross-domain works (e.g. seed with artists, ask for movies). Set birth_year to bias films/TV/books "
            "toward the resident's reminiscence bump (ages ~8-32). Results include affinity (0-1) and "
            "because_of (which seed drove each pick)."
        ),
        "input_schema": _schema(
            {
                "seed_entity_ids": {"type": "array", "items": {"type": "string"}},
                "type": {"type": "string", "enum": ["artist", "movie", "tv_show", "book"]},
                "birth_year": {"type": "integer"},
                "exclude_tag_ids": {"type": "array", "items": {"type": "string"}, "description": "Qloo tag IDs to avoid, e.g. distressing genres."},
                "take": {"type": "integer", "minimum": 1, "maximum": 15},
            },
            ["seed_entity_ids", "type"],
        ),
    },
    {
        "name": "find_outing_places",
        "description": (
            "Find real venues near the care home that fit the resident's taste. By default results are limited to "
            "calm, older-friendly daytime venues: tea rooms, museums, art galleries, parks and gardens, garden centres, "
            "theatres and concert halls, cinemas, piers and promenades, libraries. Bars, pubs, nightclubs, fast food "
            "and hotels are always excluded. Each result has a 'kind' and 'match' ('taste' = matched to the seeds, "
            "'popular locally' = well liked by over-55s nearby, used to top up thin results). Pass tag_ids "
            "(urn:tag:category:place:... from search_tags) only to target something else, e.g. a restaurant serving "
            "the food of a resident's heritage."
        ),
        "input_schema": _schema(
            {
                "seed_entity_ids": {"type": "array", "items": {"type": "string"}},
                "location": {"type": "string", "description": "Town or city of the care home, e.g. 'Brighton'."},
                "tag_ids": {"type": "array", "items": {"type": "string"}, "description": "Overrides the default venue categories (any tag matches)."},
                "exclude_tag_ids": {"type": "array", "items": {"type": "string"}, "description": "Extra venue tags to avoid, e.g. loud live-music venues."},
                "take": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            ["seed_entity_ids", "location"],
        ),
    },
    {
        "name": "search_tags",
        "description": (
            "Look up Qloo tag IDs (genres, cuisines, venue kinds) by keyword, for use with find_outing_places or "
            "exclude_tag_ids. Set places_only to get venue categories (urn:tag:category:place:...)."
        ),
        "input_schema": _schema({"query": {"type": "string"}, "places_only": {"type": "boolean"}}, ["query"]),
    },
    {
        "name": "group_common_ground",
        "description": (
            "For a group session: score candidate entities (all of one type) against EACH resident's taste and "
            "rank them by the lowest affinity across the group, so nobody is left out. Use candidates gathered from "
            "taste_recommendations for each resident."
        ),
        "input_schema": _schema(
            {
                "type": {"type": "string", "enum": ["artist", "movie", "tv_show", "book", "place"]},
                "candidate_entity_ids": {"type": "array", "items": {"type": "string"}},
                "residents": {
                    "type": "array",
                    "items": _schema(
                        {"name": {"type": "string"}, "seed_entity_ids": {"type": "array", "items": {"type": "string"}}, "birth_year": {"type": "integer"}},
                        ["name", "seed_entity_ids"],
                    ),
                },
            },
            ["type", "candidate_entity_ids", "residents"],
        ),
    },
    {
        "name": "submit_plan",
        "description": "Submit the finished activity plan. Call exactly once, at the end. Only include entities returned by Qloo tools.",
        "input_schema": _schema(
            {
                "title": {"type": "string"},
                "summary": {"type": "string", "description": "2-3 sentences for the activity coordinator."},
                "sections": {
                    "type": "array",
                    "items": _schema(
                        {
                            "kind": {"type": "string", "enum": ["music", "film", "tv", "reading", "outing", "food", "group"]},
                            "title": {"type": "string"},
                            "items": {
                                "type": "array",
                                "items": _schema(
                                    {"name": {"type": "string"}, "entity_id": {"type": "string"}, "why": {"type": "string"}},
                                    ["name", "why"],
                                ),
                            },
                        },
                        ["kind", "title", "items"],
                    ),
                },
                "conversation_prompts": {"type": "array", "items": {"type": "string"}},
                "facilitator_tips": {"type": "array", "items": {"type": "string"}},
                "cautions": {"type": "array", "items": {"type": "string"}},
            },
            ["title", "summary", "sections", "conversation_prompts", "facilitator_tips", "cautions"],
        ),
    },
]


class ToolRunner:
    def __init__(self, qloo: QlooLike) -> None:
        self.qloo = qloo
        self.qloo_calls = 0
        self.seen: dict[str, dict] = {}  # entity_id -> slim entity, for grounding checks

    def _remember(self, items: list[dict]) -> list[dict]:
        for it in items:
            if it.get("entity_id"):
                self.seen[it["entity_id"]] = it
        return items

    async def run(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            fn = getattr(self, f"t_{name}")
        except AttributeError:
            return {"error": f"Unknown tool {name}"}
        try:
            return await fn(**args)
        except (QlooError, TypeError, ValueError) as exc:
            return {"error": str(exc)}

    async def t_search_entities(self, queries: list[dict]) -> dict:
        async def one(q: dict) -> dict:
            self.qloo_calls += 1
            try:
                hits = await self.qloo.search(q["name"], q.get("type"), take=3)
            except QlooError as exc:  # one failed lookup shouldn't sink the whole batch
                return {"query": q["name"], "best": None, "alternatives": [], "error": str(exc)}
            self._remember(hits)
            return {"query": q["name"], "best": hits[0] if hits else None, "alternatives": [h["name"] for h in hits[1:3]]}

        return {"results": await asyncio.gather(*(one(q) for q in queries[:12]))}

    async def t_taste_recommendations(
        self,
        seed_entity_ids: list[str],
        type: str,
        birth_year: int | None = None,
        exclude_tag_ids: list[str] | None = None,
        take: int = 8,
    ) -> dict:
        params: dict[str, Any] = {
            "filter.type": to_urn(type),
            "signal.interests.entities": seed_entity_ids,
            "signal.demographics.age": age_band(birth_year),
            "feature.explainability": "true",
            "take": take,
        }
        window = None
        if birth_year and type in ERA_TYPES:
            lo, hi = reminiscence_window(birth_year)
            key = "filter.publication_year" if type == "book" else "filter.release_year"
            params[f"{key}.min"], params[f"{key}.max"] = lo, hi
            window = [lo, hi]
        if exclude_tag_ids:
            params["filter.exclude.tags"] = exclude_tag_ids
        self.qloo_calls += 1
        items = self._remember(await self.qloo.insights(params))
        return {"type": type, "reminiscence_window": window, "results": items}

    async def t_find_outing_places(
        self,
        seed_entity_ids: list[str],
        location: str,
        tag_ids: list[str] | None = None,
        exclude_tag_ids: list[str] | None = None,
        take: int = 6,
    ) -> dict:
        params: dict[str, Any] = {
            "filter.type": to_urn("place"),
            "filter.location.query": uk_location(location),
            "filter.tags": tag_ids or DEFAULT_OUTING_TAGS,
            "filter.exclude.tags": list(dict.fromkeys(OUTING_EXCLUDE_TAGS + (exclude_tag_ids or []))),
            "signal.interests.entities": seed_entity_ids,
            "signal.demographics.age": "55_and_older",
            "take": min(take * 2, 20),  # over-fetch a little so diversify() has a choice of kinds
        }
        self.qloo_calls += 1
        places = [{**p, "match": "taste"} for p in await self.qloo.insights(params)]
        if len(places) < take:
            # Taste signals are sparse for smaller towns (Kingston returns ~2 matches), so top up
            # with venues popular with over-55s nearby, still within the same safe categories.
            local = {k: v for k, v in params.items() if k != "signal.interests.entities"}
            self.qloo_calls += 1
            have = {p["entity_id"] for p in places}
            places += [{**p, "match": "popular locally"} for p in await self.qloo.insights(local) if p["entity_id"] not in have]
        for p in places:
            if kind := outing_kind(p):
                p["kind"] = kind
        return {"location": location, "results": self._remember(diversify(places)[:take])}

    async def t_search_tags(self, query: str, places_only: bool = False) -> dict:
        self.qloo_calls += 1
        return {"tags": await self.qloo.tags(query, tag_type="urn:tag:category:place" if places_only else None)}

    async def t_group_common_ground(self, type: str, candidate_entity_ids: list[str], residents: list[dict]) -> dict:
        async def score(r: dict) -> tuple[str, dict[str, float]]:
            params = {
                "filter.type": to_urn(type),
                "filter.results.entities": candidate_entity_ids,
                "signal.interests.entities": r["seed_entity_ids"],
                "signal.demographics.age": age_band(r.get("birth_year")),
                "take": len(candidate_entity_ids),
            }
            self.qloo_calls += 1
            items = self._remember(await self.qloo.insights(params))
            return r["name"], {it["entity_id"]: it.get("affinity", 0.0) for it in items}

        scored = dict(await asyncio.gather(*(score(r) for r in residents)))
        ranked = []
        for cid in candidate_entity_ids:
            per = {name: round(s.get(cid, 0.0), 3) for name, s in scored.items()}
            vals = list(per.values()) or [0.0]
            ranked.append(
                {
                    "entity_id": cid,
                    "name": self.seen.get(cid, {}).get("name", cid),
                    "per_resident": per,
                    "group_floor": round(min(vals), 3),
                    "group_mean": round(sum(vals) / len(vals), 3),
                }
            )
        ranked.sort(key=lambda x: (-x["group_floor"], -x["group_mean"]))
        return {"ranked": ranked}

    async def t_submit_plan(self, **plan: Any) -> dict:
        # Grounding check: flag any item whose entity_id Qloo never returned.
        ungrounded = [
            it["name"]
            for sec in plan.get("sections", [])
            for it in sec.get("items", [])
            if it.get("entity_id") and it["entity_id"] not in self.seen
        ]
        return {"accepted": True, "ungrounded_items": ungrounded}
