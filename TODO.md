# Human TODO before the deadline (Fri 30 Oct 2026, 11:45pm ET = Sat 31 Oct 03:45 UTC)

## Access and accounts
- [ ] Register on https://qloo.devpost.com ("Join Hackathon") and accept the rules.
- [ ] Request a Qloo hackathon API key: https://docs.qloo.com/reference/qloo-llm-hackathon-developer-guide#getting-your-api-key (Google Form). Optionally join the Discord: https://discord.gg/rF9PKsD5Q7
- [ ] Get an Anthropic API key, and set a spend limit on it.

## Live verification (the code was built against the docs plus mock data)
- [ ] `cp .env.example .env`, add both keys, then `set -a; source .env; set +a; uv run uvicorn app.main:app --port 8000`.
- [ ] Run Margaret (one-to-one) and the three-person group. Check that the Qloo `/search` and `/v2/insights` responses parse as expected. Field names are taken from the docs; adjust `slim_entity` in `app/qloo.py` if needed.
- [ ] Check that `filter.release_year.*`, `filter.results.entities` and `feature.explainability` behave as expected on the hackathon endpoint. Unsupported parameters are silently ignored, so an empty result can mean the parameter isn't supported.
- [ ] Note the quota and rate limits Qloo publishes, and adjust `MAX_CONCURRENT_RUNS` to match.

## Ship (required for eligibility)
- [ ] Create a **public** GitHub repo and push. Confirm the MIT licence shows in the repo's About panel.
- [ ] Deploy publicly (Render via `render.yaml`/Dockerfile, Fly.io, Railway, or Cloud Run). Store the keys as secrets, never in the repo or the browser.
- [ ] Smoke-test the public URL from a phone and a laptop. The demo must be usable by judges free of charge until 5 Nov.
- [ ] Consider adding basic abuse protection to the public demo (rate limit per IP) so judges don't exhaust the quota.

## Submit
- [ ] Fill in Devpost from `SUBMISSION.md`. Check every **[verify]** statistic first.
- [ ] Add screenshots (resident picker, live trace, finished plan, print view) and a thumbnail.
- [ ] Optional: record the 3-minute video from the script in `SUBMISSION.md`.
- [ ] Submit before the deadline, then re-open the live URL to confirm it still works.
- [ ] Finalists must be available for the live show on 5 Nov, plus prep beforehand. Block the time.
