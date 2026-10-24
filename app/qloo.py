"""Thin async client for the Qloo hackathon API.

Matches the documented hackathon surface:
  base URL  https://hackathon.api.qloo.com
  auth      X-Api-Key header
  GET /search       (query, types, take)
  GET /v2/insights  (filter.type, signal.*, filter.*, take, feature.explainability)
  GET /v2/tags      (filter.query, ...)

Results are normalised into small dicts so the agent's context stays compact.
A MockQloo with realistic fixtures is used when QLOO_API_KEY is not set.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Protocol

import httpx

from . import fixtures

HACKATHON_BASE_URL = "https://hackathon.api.qloo.com"

ENTITY_TYPES = {
    "artist": "urn:entity:artist",
    "movie": "urn:entity:movie",
    "tv_show": "urn:entity:tv_show",
    "book": "urn:entity:book",
    "place": "urn:entity:place",
    "podcast": "urn:entity:podcast",
    "brand": "urn:entity:brand",
    "destination": "urn:entity:destination",
    "locality": "urn:entity:locality",
}

AGE_BANDS = {"55_and_older", "36_to_55", "35_and_younger"}

TAG_PRIORITY = (":category:", ":genre:")
GENERIC_TAG_NAMES = {"Place"}


class QlooError(RuntimeError):
    pass


def to_urn(kind: str) -> str:
    if kind.startswith("urn:"):
        return kind
    try:
        return ENTITY_TYPES[kind]
    except KeyError as exc:
        raise QlooError(f"Unknown entity type '{kind}'. Use one of {sorted(ENTITY_TYPES)}") from exc


def slim_entity(e: dict[str, Any]) -> dict[str, Any]:
    """Keep only what the agent and UI need (Qloo responses are verbose)."""
    props = e.get("properties") or {}
    query = e.get("query") or {}
    out: dict[str, Any] = {
        "entity_id": e.get("entity_id"),
        "name": e.get("name"),
        "type": (e.get("types") or [e.get("type")])[0] if (e.get("types") or e.get("type")) else None,
        "subtype": e.get("subtype"),
    }
    for key in ("release_year", "year", "address", "description", "short_description", "business_rating", "price_level"):
        if props.get(key) not in (None, ""):
            out[key] = props[key]
    if isinstance(props.get("image"), dict) and props["image"].get("url"):
        out["image"] = props["image"]["url"]
    if e.get("popularity") is not None:
        out["popularity"] = round(float(e["popularity"]), 3)
    if query.get("affinity") is not None:
        out["affinity"] = round(float(query["affinity"]), 3)
    expl = query.get("explainability")
    if isinstance(expl, dict):
        drivers = expl.get("signal.interests.entities") or []
        if drivers:
            out["because_of"] = [
                {"entity_id": d.get("entity_id"), "score": round(float(d.get("score", 0)), 2)} for d in drivers[:3]
            ]
    tags = [t for t in e.get("tags") or [] if t.get("name")]
    if tags:
        # Places carry dozens of tags (payments, parking...) in no useful order; surface what
        # the venue *is* (category, then genre) so the agent and UI see "Tea house", not "Mastercard".
        ranked = sorted(tags, key=lambda t: next((i for i, p in enumerate(TAG_PRIORITY) if p in (t.get("id") or "")), len(TAG_PRIORITY)))
        names = dict.fromkeys(t["name"] for t in ranked if t["name"] not in GENERIC_TAG_NAMES)  # de-dupe, keep order
        out["tags"] = list(names)[:6]
    if any("wheelchair_accessible_entrance" in (t.get("id") or "") for t in tags):
        out["wheelchair_accessible"] = True
    loc = e.get("location") or {}
    if loc.get("lat") is not None:
        out["location"] = {"lat": loc.get("lat"), "lon": loc.get("lon")}
    return {k: v for k, v in out.items() if v is not None}


class QlooLike(Protocol):
    mode: str

    async def search(self, query: str, kind: str | None = None, take: int = 5) -> list[dict]: ...

    async def insights(self, params: dict[str, Any]) -> list[dict]: ...

    async def tags(self, query: str, take: int = 8, tag_type: str | None = None) -> list[dict]: ...


class QlooClient:
    mode = "live"

    def __init__(
        self,
        api_key: str,
        base_url: str = HACKATHON_BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
        cache_ttl: float = 900.0,
        retry_delay: float = 1.0,
        max_concurrency: int = 4,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"X-Api-Key": api_key, "Accept": "application/json"},
            timeout=20.0,
            transport=transport,
        )
        self._cache: dict[tuple, tuple[float, Any]] = {}
        self._ttl = cache_ttl
        self._retry_delay = retry_delay
        self._gate = asyncio.Semaphore(max_concurrency)  # the hackathon key rate-limits bursts of parallel calls

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict[str, Any]) -> dict:
        clean = {k: (",".join(map(str, v)) if isinstance(v, (list, tuple)) else v) for k, v in params.items() if v not in (None, "", [])}
        key = (path, tuple(sorted((k, str(v)) for k, v in clean.items())))
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < self._ttl:
            return hit[1]
        for attempt in range(2):  # bounded retry, per hackathon safe-use rules
            async with self._gate:
                resp = await self._client.get(path, params=clean)
            if resp.status_code == 429 and attempt == 0:
                try:
                    wait = float(resp.headers.get("retry-after", self._retry_delay))
                except ValueError:
                    wait = self._retry_delay
                await asyncio.sleep(min(wait, 5.0))  # back off before the single retry
                continue
            break
        if resp.status_code == 404:
            data: dict = {"results": []}
        elif resp.status_code >= 400:
            raise QlooError(f"Qloo {path} returned {resp.status_code}: {resp.text[:200]}")
        else:
            data = resp.json()
        self._cache[key] = (time.monotonic(), data)
        return data

    async def search(self, query: str, kind: str | None = None, take: int = 5) -> list[dict]:
        params: dict[str, Any] = {"query": query, "take": take}
        if kind:
            params["types"] = to_urn(kind)
        data = await self._get("/search", params)
        results = data.get("results") or []
        if isinstance(results, dict):
            results = results.get("entities") or []
        return [slim_entity(e) for e in results]

    async def insights(self, params: dict[str, Any]) -> list[dict]:
        data = await self._get("/v2/insights", params)
        results = data.get("results") or {}
        entities = results.get("entities") if isinstance(results, dict) else results
        return [slim_entity(e) for e in entities or []]

    async def tags(self, query: str, take: int = 8, tag_type: str | None = None) -> list[dict]:
        data = await self._get("/v2/tags", {"filter.query": query, "filter.tag.types": tag_type, "take": take})
        results = data.get("results") or {}
        tags = results.get("tags") if isinstance(results, dict) else results
        return [{"id": t.get("id"), "name": t.get("name"), "type": t.get("type")} for t in tags or []]


class MockQloo:
    """Deterministic stand-in that returns realistic, Qloo-shaped data."""

    mode = "mock"

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def aclose(self) -> None:  # parity with QlooClient
        return None

    async def search(self, query: str, kind: str | None = None, take: int = 5) -> list[dict]:
        self.calls.append(("/search", {"query": query, "types": kind}))
        return [slim_entity(e) for e in fixtures.mock_search(query, to_urn(kind) if kind else None)[:take]]

    async def insights(self, params: dict[str, Any]) -> list[dict]:
        self.calls.append(("/v2/insights", dict(params)))
        return [slim_entity(e) for e in fixtures.mock_insights(params)]

    async def tags(self, query: str, take: int = 8, tag_type: str | None = None) -> list[dict]:
        self.calls.append(("/v2/tags", {"filter.query": query, "filter.tag.types": tag_type}))
        return fixtures.mock_tags(query, tag_type)[:take]


def build_qloo(api_key: str | None, base_url: str | None = None) -> QlooLike:
    if api_key:
        return QlooClient(api_key, base_url or HACKATHON_BASE_URL)
    return MockQloo()
