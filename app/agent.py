"""The Encore planning agent.

LiveAgent: Claude (tool use) decides which Qloo calls to make and composes the plan.
ScriptedAgent: deterministic planner used when ANTHROPIC_API_KEY is absent. It drives
the *same* tools, so the Qloo integration and UI are exercised end-to-end.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Literal

from pydantic import BaseModel, Field

from .tools import TOOL_DEFS, ToolRunner, reminiscence_window

DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_TURNS = 14

Event = dict[str, Any]


class Favourite(BaseModel):
    name: str
    type: Literal["artist", "movie", "tv_show", "book", "place"]


class Resident(BaseModel):
    id: str
    name: str = Field(description="Preferred name only; no surnames needed.")
    birth_year: int = Field(ge=1915, le=2010)
    hometown: str = ""
    background: str = ""
    favourites: list[Favourite] = Field(min_length=1, max_length=10)
    avoid: list[str] = []


class PlanRequest(BaseModel):
    residents: list[Resident] = Field(min_length=1, max_length=6)
    location: str = Field(default="Brighton", max_length=80)
    session: Literal["one_to_one", "group", "outing"] = "one_to_one"
    notes: str = Field(default="", max_length=500)


SYSTEM_PROMPT = """You are Encore, an activity-planning agent for care-home activity coordinators \
working with people living with dementia.

Your job: turn a few known favourites into a personalised, ready-to-run reminiscence session, \
grounded in Qloo's cultural taste graph rather than generic guesses.

How to work:
1. Resolve every favourite to a Qloo entity with search_entities (one batched call).
2. Use taste_recommendations to expand each resident's taste ACROSS domains (music -> films, \
films -> TV, etc.). Pass birth_year so films/TV/books land in their reminiscence bump.
3. For outings, use find_outing_places near the care home location. Its defaults already keep to calm, \
daytime, older-friendly venues; only pass tag_ids for something specific (e.g. food from a resident's heritage).
4. For group sessions, collect candidates per resident, then call group_common_ground and prefer \
items with the highest group_floor so nobody is left out.
5. Finish by calling submit_plan exactly once.

Rules:
- Only recommend entities that Qloo tools returned; include their entity_id.
- Each item's "why" must cite the resident's actual favourite it connects to (use because_of / affinity).
- Respect every "avoid" item (e.g. war films, loud venues) and say how you honoured it in cautions.
- Conversation prompts must be open, gentle, sensory and never test memory ("Do you remember...?" \
is discouraged; prefer "What was it like when...").
- Facilitator tips: practical (volume, time of day, session length 20-40 min, props, food textures).
- Use British English. Be concise. Make parallel tool calls where possible."""


def describe_request(req: PlanRequest) -> str:
    lines = [f"Session type: {req.session}. Care home location: {req.location}."]
    if req.notes:
        lines.append(f"Coordinator notes: {req.notes}")
    for r in req.residents:
        lo, hi = reminiscence_window(r.birth_year)
        favs = "; ".join(f"{f.name} ({f.type})" for f in r.favourites)
        lines.append(
            f"- {r.name}, born {r.birth_year} (reminiscence window {lo}-{hi}), from {r.hometown or 'unknown'}. "
            f"Background: {r.background or 'n/a'}. Favourites: {favs}. Avoid: {', '.join(r.avoid) or 'none'}."
        )
    return "\n".join(lines)


def summarise_result(name: str, result: dict) -> str:
    if "error" in result:
        return f"error: {result['error']}"
    if name == "search_entities":
        found = [r["best"]["name"] for r in result["results"] if r.get("best")]
        missed = [r["query"] for r in result["results"] if not r.get("best")]
        return f"resolved {len(found)}: " + ", ".join(found) + (f" (not found: {', '.join(missed)})" if missed else "")
    if name in ("taste_recommendations", "find_outing_places"):
        items = result.get("results", [])
        top = ", ".join(f"{i['name']} ({i.get('affinity', 0):.2f})" for i in items[:4])
        return f"{len(items)} results: {top}"
    if name == "group_common_ground":
        top = ", ".join(f"{i['name']} (floor {i['group_floor']:.2f})" for i in result["ranked"][:3])
        return f"ranked {len(result['ranked'])}: {top}"
    if name == "search_tags":
        return ", ".join(t["name"] for t in result.get("tags", [])[:5])
    if name == "submit_plan":
        return "plan accepted" + (f" (ungrounded: {result['ungrounded_items']})" if result.get("ungrounded_items") else "")
    return "ok"


class ScriptedAgent:
    """Deterministic planner for keyless demos and tests."""

    mode = "scripted"

    def __init__(self, tools: ToolRunner) -> None:
        self.tools = tools

    async def _call(self, name: str, args: dict) -> tuple[list[Event], dict]:
        result = await self.tools.run(name, args)
        return (
            [
                {"type": "tool_call", "name": name, "input": args},
                {"type": "tool_result", "name": name, "summary": summarise_result(name, result)},
            ],
            result,
        )

    async def run(self, req: PlanRequest) -> AsyncIterator[Event]:
        yield {"type": "message", "text": "Resolving each resident's favourites in Qloo's taste graph."}
        seeds: dict[str, list[dict]] = {}
        for r in req.residents:
            evs, res = await self._call("search_entities", {"queries": [f.model_dump() for f in r.favourites]})
            for e in evs:
                yield e
            seeds[r.id] = [x["best"] for x in res.get("results", []) if x.get("best")]

        picks: dict[str, dict[str, list[dict]]] = {}
        for r in req.residents:
            ids = [s["entity_id"] for s in seeds[r.id]]
            picks[r.id] = {}
            yield {"type": "message", "text": f"Expanding {r.name}'s taste across music, film and TV (era {reminiscence_window(r.birth_year)[0]}-{reminiscence_window(r.birth_year)[1]})."}
            calls = [
                ("taste_recommendations", {"seed_entity_ids": ids, "type": t, "birth_year": r.birth_year, "take": 6})
                for t in ("artist", "movie", "tv_show")
            ]
            results = await asyncio.gather(*(self._call(n, a) for n, a in calls))
            for (_, a), (evs, res) in zip(calls, results):
                for e in evs:
                    yield e
                avoid = " ".join(r.avoid).lower()
                picks[r.id][a["type"]] = [
                    i for i in res.get("results", []) if not any(t.lower() in avoid for t in i.get("tags", []))
                ]

        all_ids = [s["entity_id"] for r in req.residents for s in seeds[r.id]][:8]
        evs, res = await self._call("find_outing_places", {"seed_entity_ids": all_ids, "location": req.location, "take": 4})
        for e in evs:
            yield e
        places: list[dict] = res.get("results", [])

        group_music: list[dict] = []
        if len(req.residents) > 1:
            yield {"type": "message", "text": "Finding common ground so nobody in the group is left out."}
            cands = list({i["entity_id"]: i for r in req.residents for i in picks[r.id]["artist"][:4]}.keys())
            evs, res = await self._call(
                "group_common_ground",
                {
                    "type": "artist",
                    "candidate_entity_ids": cands,
                    "residents": [
                        {"name": r.name, "seed_entity_ids": [s["entity_id"] for s in seeds[r.id]], "birth_year": r.birth_year}
                        for r in req.residents
                    ],
                },
            )
            for e in evs:
                yield e
            group_music = res.get("ranked", [])[:4]

        plan = self._compose(req, seeds, picks, places, group_music)
        evs, _ = await self._call("submit_plan", plan)
        for e in evs:
            yield e
        yield {"type": "plan", "plan": plan}

    def _why(self, item: dict, seeds: list[dict]) -> str:
        names = {s["entity_id"]: s["name"] for s in seeds}
        drivers = [names[d["entity_id"]] for d in item.get("because_of", []) if d["entity_id"] in names]
        aff = item.get("affinity")
        base = f"Taste-graph neighbour of {drivers[0]}" if drivers else "Strong taste-graph match"
        return base + (f" (affinity {aff:.2f})." if aff is not None else ".")

    @staticmethod
    def _place_why(pl: dict) -> str:
        kind = (pl.get("kind") or ", ".join(pl.get("tags", [])[:2]) or "Local venue").capitalize()
        if pl.get("wheelchair_accessible"):
            kind += ", wheelchair-accessible entrance"
        reason = "matches their taste" if pl.get("match") == "taste" else "popular with over-55s nearby"
        aff = pl.get("affinity")
        return f"{kind} - {reason}" + (f" (affinity {aff:.2f})." if aff is not None else ".")

    def _compose(self, req, seeds, picks, places, group_music) -> dict:
        names = " & ".join(r.name for r in req.residents)
        sections: list[dict] = []
        if group_music:
            sections.append(
                {
                    "kind": "group",
                    "title": "Shared sing-along (scored for everyone)",
                    "items": [
                        {"name": g["name"], "entity_id": g["entity_id"], "why": "Lowest affinity across the group is "
                         f"{g['group_floor']:.2f}: " + ", ".join(f"{k} {v:.2f}" for k, v in g["per_resident"].items())}
                        for g in group_music
                    ],
                }
            )
        for r in req.residents:
            p, s = picks[r.id], seeds[r.id]
            if not group_music:
                sections.append({"kind": "music", "title": f"{r.name}'s playlist", "items": [
                    {"name": i["name"], "entity_id": i["entity_id"], "why": self._why(i, s)} for i in p["artist"][:5]]})
            sections.append({"kind": "film", "title": f"Film afternoon for {r.name}", "items": [
                {"name": f"{i['name']} ({i.get('release_year', '')})", "entity_id": i["entity_id"], "why": self._why(i, s)} for i in p["movie"][:3]]})
            sections.append({"kind": "tv", "title": f"Familiar TV for {r.name}", "items": [
                {"name": i["name"], "entity_id": i["entity_id"], "why": self._why(i, s)} for i in p["tv_show"][:2]]})
        if places:
            sections.append({"kind": "outing", "title": f"Outing ideas near {req.location}", "items": [
                {"name": pl["name"], "entity_id": pl["entity_id"], "why": self._place_why(pl)} for pl in places[:3]]})
        first = req.residents[0]
        fav = first.favourites[0].name
        return {
            "title": f"Encore session plan for {names}",
            "summary": (
                f"A {req.session.replace('_', ' ')} session built from {sum(len(s) for s in seeds.values())} known favourites, "
                "expanded through Qloo's taste graph into music, films, TV and outings from each person's reminiscence years."
            ),
            "sections": sections,
            "conversation_prompts": [
                f"What did it feel like the first time you heard {fav}?",
                f"Tell me about Saturday nights in {first.hometown or 'your town'} when you were young.",
                "Which song would you have danced to, and who with?",
                "What was your favourite thing to eat at the seaside or on a day out?",
            ],
            "facilitator_tips": [
                "Keep it to 30-40 minutes, mid-morning or early afternoon, before late-day fatigue.",
                "Play music at a moderate volume; let residents lead with tapping, humming or singing.",
                "Bring props: song-sheet lyrics in large print, a programme or record sleeve, a scarf for dancing.",
                "Offer soft-textured treats (e.g. Victoria sponge) and a hot drink to anchor the senses.",
            ],
            "cautions": [f"{r.name}: avoided {', '.join(r.avoid)}." for r in req.residents if r.avoid]
            or ["Watch for signs of distress; switch to a familiar upbeat song if mood dips."],
        }


class LiveAgent:
    """Claude tool-use loop over the Qloo tools."""

    mode = "live"

    def __init__(self, tools: ToolRunner, api_key: str | None = None, model: str = DEFAULT_MODEL, client: Any = None) -> None:
        self.tools = tools
        self.model = model
        if client is None:
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic(api_key=api_key)
        self.client = client

    async def run(self, req: PlanRequest) -> AsyncIterator[Event]:
        messages: list[dict] = [{"role": "user", "content": describe_request(req)}]
        for _ in range(MAX_TURNS):
            response = await self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                tools=TOOL_DEFS,
                messages=messages,
                output_config={"effort": "medium"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            for block in response.content:
                if block.type == "text" and block.text.strip():
                    yield {"type": "message", "text": block.text.strip()}

            if response.stop_reason == "refusal":
                yield {"type": "error", "message": "The model declined this request."}
                return
            if response.stop_reason == "max_tokens":
                yield {"type": "error", "message": "The model ran out of output tokens."}
                return

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                yield {"type": "error", "message": "Agent finished without submitting a plan."}
                return

            messages.append({"role": "assistant", "content": response.content})
            for tu in tool_uses:
                yield {"type": "tool_call", "name": tu.name, "input": tu.input}
            results = await asyncio.gather(*(self.tools.run(tu.name, dict(tu.input)) for tu in tool_uses))

            plan = None
            tool_results = []
            for tu, res in zip(tool_uses, results):
                yield {"type": "tool_result", "name": tu.name, "summary": summarise_result(tu.name, res)}
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": tu.id, "content": json.dumps(res), "is_error": "error" in res}
                )
                if tu.name == "submit_plan" and res.get("accepted"):
                    plan = dict(tu.input)
            if plan is not None:
                yield {"type": "plan", "plan": plan}
                return
            messages.append({"role": "user", "content": tool_results})
        yield {"type": "error", "message": "Agent hit the turn limit."}
