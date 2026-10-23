"""FastAPI app: serves the UI and streams agent runs as Server-Sent Events."""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .agent import DEFAULT_MODEL, LiveAgent, PlanRequest, ScriptedAgent
from .qloo import build_qloo
from .tools import ToolRunner

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "data" / "residents.json"
MAX_CONCURRENT_RUNS = int(os.getenv("MAX_CONCURRENT_RUNS", "4"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.qloo = build_qloo(os.getenv("QLOO_API_KEY"), os.getenv("QLOO_BASE_URL"))
    app.state.anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    app.state.model = os.getenv("ENCORE_MODEL", DEFAULT_MODEL)
    app.state.gate = asyncio.Semaphore(MAX_CONCURRENT_RUNS)
    yield
    await app.state.qloo.aclose()


app = FastAPI(title="Encore", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "qloo": app.state.qloo.mode,
        "agent": "live" if app.state.anthropic_key else "scripted",
        "model": app.state.model if app.state.anthropic_key else None,
    }


@app.get("/api/residents")
async def residents() -> JSONResponse:
    return JSONResponse(json.loads(DATA.read_text()))


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@app.post("/api/plan")
async def plan(req: PlanRequest) -> StreamingResponse:
    async def stream():
        async with app.state.gate:
            tools = ToolRunner(app.state.qloo)
            agent = (
                LiveAgent(tools, app.state.anthropic_key, app.state.model)
                if app.state.anthropic_key
                else ScriptedAgent(tools)
            )
            yield _sse({"type": "start", "agent": agent.mode, "qloo": app.state.qloo.mode})
            try:
                async for event in agent.run(req):
                    yield _sse(event)
            except Exception as exc:  # surface failures to the UI instead of a dead stream
                yield _sse({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
            yield _sse({"type": "done", "qloo_calls": tools.qloo_calls})

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
