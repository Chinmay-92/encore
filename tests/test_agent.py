import json
from pathlib import Path
from types import SimpleNamespace as NS

from app.agent import DEFAULT_MODEL, LiveAgent, PlanRequest, ScriptedAgent, describe_request
from app.qloo import MockQloo
from app.tools import ToolRunner

RESIDENTS = json.loads((Path(__file__).parents[1] / "data" / "residents.json").read_text())


async def collect(agen):
    return [e async for e in agen]


async def test_scripted_one_to_one_plan_is_grounded_and_respects_avoid():
    tr = ToolRunner(MockQloo())
    req = PlanRequest(residents=[RESIDENTS[0]], session="one_to_one", location="Brighton")
    events = await collect(ScriptedAgent(tr).run(req))
    plan = next(e["plan"] for e in events if e["type"] == "plan")
    items = [it for s in plan["sections"] for it in s["items"]]
    assert items and all(it["entity_id"] in tr.seen for it in items)
    assert not any("Dam Busters" in it["name"] for it in items)  # Margaret avoids war films
    assert {s["kind"] for s in plan["sections"]} >= {"music", "film", "tv", "outing"}
    assert tr.qloo_calls >= 5
    assert any(e["type"] == "tool_call" and e["name"] == "taste_recommendations" for e in events)


async def test_scripted_group_uses_common_ground():
    tr = ToolRunner(MockQloo())
    req = PlanRequest(residents=RESIDENTS, session="group")
    events = await collect(ScriptedAgent(tr).run(req))
    assert any(e["type"] == "tool_call" and e["name"] == "group_common_ground" for e in events)
    plan = next(e["plan"] for e in events if e["type"] == "plan")
    assert plan["sections"][0]["kind"] == "group"


def test_describe_request_mentions_window_and_avoid():
    text = describe_request(PlanRequest(residents=[RESIDENTS[0]]))
    assert "1949-1973" in text and "war films" in text


class FakeMessages:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def create(self, **kw):
        self.calls.append(kw)
        return self.script.pop(0)


def tool_use(id, name, input):
    return NS(type="tool_use", id=id, name=name, input=input)


async def test_live_agent_loop_runs_tools_and_returns_plan():
    plan = {"title": "T", "summary": "S", "sections": [], "conversation_prompts": ["p"], "facilitator_tips": ["t"], "cautions": []}
    msgs = FakeMessages([
        NS(stop_reason="tool_use", content=[NS(type="text", text="Looking up favourites."),
                                            tool_use("t1", "search_entities", {"queries": [{"name": "Elvis Presley", "type": "artist"}]})]),
        NS(stop_reason="tool_use", content=[tool_use("t2", "submit_plan", plan)]),
    ])
    client = NS(beta=NS(messages=msgs))
    tr = ToolRunner(MockQloo())
    events = await collect(LiveAgent(tr, client=client).run(PlanRequest(residents=[RESIDENTS[0]])))
    types = [e["type"] for e in events]
    assert types == ["message", "tool_call", "tool_result", "tool_call", "tool_result", "plan"]
    first = msgs.calls[0]
    assert first["model"] == DEFAULT_MODEL == "claude-sonnet-5-5"
    assert first["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in first["betas"]
    second = msgs.calls[1]["messages"]
    assert second[2]["role"] == "user" and second[2]["content"][0]["tool_use_id"] == "t1"


async def test_live_agent_handles_refusal():
    msgs = FakeMessages([NS(stop_reason="refusal", content=[])])
    events = await collect(LiveAgent(ToolRunner(MockQloo()), client=NS(beta=NS(messages=msgs))).run(PlanRequest(residents=[RESIDENTS[0]])))
    assert events[-1]["type"] == "error"
