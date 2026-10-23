# Devpost submission draft: Encore

> Statistics marked **[verify]** must be checked against a primary source before you paste them into Devpost.

**Tagline:** Agents with taste, for the people who need it most. Encore turns three favourites into a whole afternoon of memories.

## Inspiration

Music and familiar culture are among the most reliable ways to reach someone living with dementia. A song from someone's teenage years can bring back recognition, conversation and even dancing, at a point when much else has faded. Care homes know this, and activity coordinators run reminiscence sessions every week. In practice, though, the same generic playlist gets used for everyone. A coordinator with 40 residents can't research what a former seamstress from Brighton, a Jamaican-born bus conductor and a Punjabi shopkeeper would each have loved at 18.

When you ask an LLM, you get the stereotype ("Vera Lynn and *Casablanca*"). What's missing is taste: knowing that someone who loves Doris Day and *The Sound of Music* is likely to light up for Matt Monro, *Summer Holiday* and *Come Dancing*. That knowledge is what Qloo's taste graph holds.

## What it does

1. A coordinator picks one or more residents. Each has a first name, a birth year, where they grew up, a few known favourites, and things to avoid.
2. The Encore agent resolves the favourites to Qloo entities and then expands each person's taste **across domains** (music, films, TV, books). It pins films, TV and books to the person's **reminiscence bump**, roughly ages 8-32, the period whose memories survive longest.
3. For **group sessions**, the agent scores every candidate song against *each* resident and ranks by the lowest score. The shared sing-along then works for everyone, not just the majority.
4. It finds **real outings near the care home** that fit the group's taste: tea dances, bandstands, classic cinemas, and restaurants serving the food of a resident's heritage.
5. It writes a printable session sheet: a playlist, a film afternoon and familiar TV, each with a "because they love X" reason taken from Qloo's explainability data. The sheet also includes gentle conversation starters that never test memory, practical facilitator tips (timing, volume, props, food textures), and a record of how each resident's sensitivities were respected.

You can watch the agent work live: every Qloo call streams into the "Agent at work" panel.

## How we built it

- **Qloo Insights API** (hackathon endpoint, `X-Api-Key`):
  - `/search` resolves entities.
  - `/v2/insights` handles cross-domain recommendations, using `signal.interests.entities`, `signal.demographics.age`, `filter.release_year.*` / `filter.publication_year.*`, `filter.location.query` for places, `filter.results.entities` for per-resident scoring, `filter.exclude.tags`, and `feature.explainability`.
  - `/v2/tags` looks up tag IDs.
- **Agent:** Claude (`claude-sonnet-5-5`) runs a tool-use loop over six tools: five Qloo-backed tools plus a structured `submit_plan`. Server-side refusal fallback is enabled. A grounding check flags any recommended item that Qloo didn't return.
- **Backend:** Python, FastAPI and httpx, streaming the agent's steps to the browser over Server-Sent Events. It caches Qloo responses, retries a 429 once, and limits how many runs can happen at once, to respect the hackathon quota.
- **Frontend:** dependency-free HTML, CSS and JS, designed for tablets in a care-home lounge. It uses large hyperlegible type, supports dark mode, and has a print stylesheet that turns the plan into a one-page session sheet.
- **Mock mode:** Qloo-shaped fixtures and a scripted planner let the full product run without any keys, for tests and for judges.
- **Tests:** a 21-test pytest suite covering the API contract, the agent loop and the end-to-end SSE stream.

## Challenges we ran into

- **Quota and latency:** the agent calls Qloo up to about 25 times for a three-person group. We batch entity resolution, run independent Qloo calls in parallel, and cache responses.
- **Group fairness:** averaging affinities let the majority's taste drown out one person. Ranking by the lowest per-resident affinity fixed this.
- **Tone:** reminiscence work has clinical best practice behind it. "Do you remember...?" can cause distress. We encoded the guidance into the agent's instructions and the plan structure.

## Accomplishments that we're proud of

- Every recommendation is grounded in Qloo and explained: "because she loves Doris Day (affinity 0.82)".
- Cross-domain taste (music to film to outings) plus the age-window filtering produces recommendations an LLM alone doesn't.
- It's a complete product, not a notebook: it runs end to end, prints, and works without keys in demo mode.

## What we learned

- Qloo's `feature.explainability` turns a black-box recommendation into something a care worker can trust and explain to family.
- `filter.results.entities` is an underrated primitive: it lets you ask "how much would *this* person like *these* things?", which is exactly what group planning needs.

## What's next for Encore

- A **family intake link**, so relatives can add favourites and stories before admission.
- **Session feedback** ("Margaret sang along to Matt Monro") that feeds back in as stronger signals.
- **Integrations:** music streaming playlists, care-planning software (for example Person Centred Software or Nourish **[verify names]**), and dementia-friendly cinema listings.
- Pilots with two or three UK care homes, measuring engagement and agitation incidents.

## Built with

`qloo-insights-api` · `claude` · `anthropic-sdk` · `python` · `fastapi` · `httpx` · `server-sent-events` · `javascript` · `html5` · `css3` · `docker` · `pytest`

## Custom form answers

- **When did you begin your project?** 23 October 2026
- **Public URL:** `<deployed URL>`
- **Public code repo:** `<GitHub URL>` (make sure the MIT licence shows in the repo's About panel)
- **Existing project?** No, this is new for the hackathon.

## Business pitch (one paragraph)

There are around 900,000 people living with dementia in the UK **[verify]**, and most care-home residents have dementia **[verify %]**. Engagement is a regulated quality measure (CQC inspects for person-centred activities **[verify wording]**), yet activity coordinators have almost no tooling. Encore is a B2B SaaS tool for care-home groups. We'd charge per home per month, for example £49-£99 **[validate]**, which is less than the cost of an hour of agency staff time a week. Because the product only works with taste data, Qloo is the moat: anyone can wrap an LLM, but turning three favourites into a culturally accurate afternoon needs a taste graph. We'd start with UK care homes, then expand to domiciliary care, hospitals' dementia wards, and the US memory-care market. The same engine could later serve family caregivers as a consumer app.

## 3-minute demo video script (optional: Devpost doesn't require a video, but it helps on the live show)

| Time | Visual | Voice-over |
|---|---|---|
| 0:00-0:20 | Title card, then a photo-free illustration of a care-home lounge | "Music can reach people with dementia when almost nothing else can. But the playlist has to be *theirs*. Ask an AI, and every 85-year-old gets Vera Lynn." |
| 0:20-0:40 | The Encore UI, with resident cards | "Encore is an agent for care-home activity coordinators. Margaret was born in 1941, grew up in Brighton, loves Elvis, Doris Day and *The Sound of Music*, and shouldn't be shown war films." |
| 0:40-1:20 | Click **Plan the session**; the trace streams | "The agent resolves her favourites in Qloo's taste graph, then expands her taste across domains, pinned to 1949-1973, her reminiscence bump. Every one of these calls goes to Qloo." |
| 1:20-1:50 | The plan cards | "Matt Monro, *Summer Holiday*, *Come Dancing*. Each comes with a reason: because she loves Doris Day. There's an outing to a tea dance nearby, conversation starters that never test memory, and no war films." |
| 1:50-2:30 | Select Margaret, Winston and Harjit; choose Small group; run | "Groups are harder. A Jamaican-born bus conductor and a Punjabi shopkeeper don't share Margaret's playlist. Encore scores every song against each person and ranks by the *lowest* score, so the sing-along works for everyone." |
| 2:30-2:45 | Print preview | "One click prints the session sheet." |
| 2:45-3:00 | Closing card: Encore, plus the Qloo and Claude logos | "Encore: agents with taste, for the people who need it most." |
