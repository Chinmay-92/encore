# Encore: reminiscence sessions with taste

Encore is an agent that plans personalised reminiscence sessions for people living with dementia. A care-home activity coordinator enters a few things a resident is known to love, for example *Elvis, Doris Day, The Sound of Music*. The agent then uses **Qloo's taste graph** to work out what else that person is likely to love: songs, films, TV, books and local outings from their own formative years. It returns a printable session plan with gentle conversation starters, facilitator tips, and a record of how each resident's sensitivities were respected.

Built for the [Qloo Agentic Hackathon](https://qloo.devpost.com/) (deadline 30 Oct 2026, 11:45pm ET).

## Why Qloo matters here

An LLM on its own guesses: it gives every 85-year-old "Vera Lynn and *Casablanca*". Encore works differently:

| Step | Qloo call |
|---|---|
| Resolve each favourite to a real entity | `GET /search?query=&types=urn:entity:artist` |
| Expand taste **across domains** (music to film to TV to books) | `GET /v2/insights` with `filter.type`, `signal.interests.entities`, `signal.demographics.age`, `feature.explainability=true` |
| Pin media to the **reminiscence bump** (ages about 8-32, when memories are most durable) | `filter.release_year.min/max` (`filter.publication_year.*` for books) |
| Find venues near the care home that suit the resident's taste, limited to calm daytime places (tea rooms, museums, galleries, parks and gardens, garden centres, theatres, cinemas, piers, libraries), never bars, pubs, nightclubs, fast food or hotels | `filter.type=urn:entity:place` + `filter.location.query` + `filter.tags` (category tags, OR) + `filter.exclude.tags`; a second call without taste signals tops up thin results |
| **Group sessions:** score candidates against *each* resident and rank by the lowest score, so nobody is left out | `filter.results.entities` + per-resident `signal.interests.entities` |
| Avoid triggers | `filter.exclude.tags` (agent-driven) |

Each recommendation carries a "why". It comes from Qloo's `query.explainability`, which records which favourite drove the pick, and from the affinity score. A grounding check flags any plan item that Qloo never returned.

## Architecture

```
Browser (vanilla JS, SSE)  ->  FastAPI  ->  Agent loop (Claude claude-sonnet-5-5, tool use)
                                               |-- search_entities      -> Qloo /search
                                               |-- taste_recommendations -> Qloo /v2/insights
                                               |-- find_outing_places    -> Qloo /v2/insights (places)
                                               |-- search_tags           -> Qloo /v2/tags
                                               |-- group_common_ground   -> Qloo /v2/insights (filter.results.entities)
                                               `-- submit_plan           (structured output + grounding check)
```

- `app/qloo.py`: async Qloo client. It sends the `X-Api-Key` header, uses the base URL `https://hackathon.api.qloo.com`, keeps a 15-minute cache, retries once on 429, and trims Qloo's verbose responses down to the fields the agent needs.
- `app/tools.py`: the tool schemas (strict JSON Schema) and their implementations.
- `app/agent.py`: `LiveAgent` (Claude tool-use loop, with server-side refusal fallback enabled) and `ScriptedAgent`, a deterministic planner that drives the same tools when no LLM key is set.
- `app/fixtures.py`: realistic mock Qloo data, used when `QLOO_API_KEY` is unset.
- `app/static/`: the UI. It uses large type (Atkinson Hyperlegible), supports dark mode, and has a print stylesheet so the plan can go on paper.

## Run locally

Requires [uv](https://docs.astral.sh/uv/). The app runs on Python 3.12 or later.

```bash
uv sync
cp .env.example .env    # optional: add keys; with no keys it runs fully in mock mode
set -a; source .env; set +a
uv run uvicorn app.main:app --reload --port 8000
# open http://localhost:8000
```

| Env var | Effect |
|---|---|
| `QLOO_API_KEY` | Live Qloo hackathon API. Without it, mock fixtures are used. |
| `ANTHROPIC_API_KEY` | Live Claude agent (`ENCORE_MODEL`, default `claude-sonnet-5-5`). Without it, the scripted planner runs. |
| `QLOO_BASE_URL` | Defaults to `https://hackathon.api.qloo.com` |
| `MAX_CONCURRENT_RUNS` | Caps parallel agent runs (protects quota). Default 4. |

The header pills in the UI show which mode is active.

## Test

```bash
uv run pytest -q
```

The tests cover the Qloo request shape (path, header, parameter encoding), parsing, caching, 404/429/500 handling, the reminiscence-window maths, the group "floor" ranking, the grounding check, the Claude tool loop (with a fake client), refusal handling, and the full SSE API in mock mode.

## Deploy

The repo includes a `Dockerfile` (and a `render.yaml` for Render). Any container host will work, for example Render, Fly.io, Railway or Cloud Run. Set `QLOO_API_KEY` and `ANTHROPIC_API_KEY` as secrets, and use `/api/health` as the health check.

## Responsible use

- Use first names only. Nothing is persisted server-side.
- Qloo returns aggregate cultural affinities, not facts about an individual. The coordinator stays in the loop and the plan is a suggestion.
- Prompts are written to avoid "testing" memory, and the residents' "avoid" lists are honoured and reported back in the plan.

## Licence

MIT. See [LICENSE](LICENSE).
