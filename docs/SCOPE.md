# Locked scope: Activities Advisor

Decision: use a single-city, single-date activity-planning agent with a web UI, replacing the customer-support scenario. External information comes from OpenWeather and Tavily. The approval workflow later accepts an itinerary; it never implies ticket booking or payment.

## Clip 2 baseline

- One configurable OpenAI model; default matches the previously working model, gpt-4.1.
- Four model-selectable tools: location resolution, forecast lookup, activity search, page extraction.
- Date-aware forecasts within provider coverage; clear limitations otherwise.
- Three to five suggested activities, evidence links and conversational revisions.
- Recent conversation state, minimal tool activity, timeout/turn budgets and source-ID validation.
- Simple web UI served by the same FastAPI application. Local-only session isolation and SQLite.

There is no custom weather/search service, helpdesk, order system, booking platform or payment integration. Source extraction can fail, and reading a page does not prove availability. Source provenance is enforced; semantic correctness must be evaluated.

## Planned course progression (not implemented in the baseline)

| Clip | Concrete later lesson |
|---|---|
| M1 C1 | Introduce local success versus production demands through the travel-planning scenario. |
| M1 C2 | Demonstrate this baseline and a conversational revision. |
| M1 C3 | Containerize; deploy FastAPI/UI to Cloud Run; add external shared state, managed secrets, and deployment access control. |
| M1 C4 | Add and compare routing against the single-model baseline. |
| M1 C5 | Add compatible-request semantic caching with expiry, meaningful context compression, token reduction, independent async work and offline batching. |
| M1 C6 | Persist a versioned proposed itinerary and execution checkpoint. Pause for human approval; restart service; resume and finalize the approved version once. |
| M1 C7 | Load-test and measure latency, throughput, reliability, costs, completion/approval rates and user feedback; discuss provider quotas and horizontal scaling. |
| M2 C1 | Contrast a convincing itinerary with an incorrect tool trajectory. |
| M2 C2 | Evaluate observable planning decisions, tool arguments/results, location/date selection, evidence and preference adherence. No private reasoning extraction. |
| M2 C3 | Build normal, ambiguous, constrained and failure-case datasets; use recorded provider responses for repeatable tests. |
| M2 C4 | Compare before/after a prompt, model, tool or workflow change. Separate live integration checks from deterministic regressions. |
| M2 C5 | Measure cost per accepted plan, time to acceptance, revisions, abandonment and explicit satisfaction. Acceptance is not proof of quality. |
| M3 C1 | Extend basic activity into correlated model/tool/retrieval/memory/checkpoint spans, with human handoff/resumption. |
| M3 C2 | Build dashboards from captured measurements. Label any synthetic traffic. |
| M3 C3 | Alert on failures, repeated searches, cost/turn overruns, injection attempts and approval bypass attempts. |
| M3 C4 | Compare behavior over time with a fixed workload and version metadata; separate environmental changes from agent regressions. |
| M3 C5 | Reproduce a regression, contain it and roll back an application/configuration version. |
| M3 C6 | Convert a rejected plan or user report into an evaluation case; fix and verify. |

## Required design rules for later work

- External APIs stay behind `Providers`; routing belongs behind `Model`; storage behind `Store`. Later additions extend this project rather than switching to the old support app.
- Keep immutable source results/timestamps and city/date/preference constraints with each evaluated run.
- Semantic cache hits must match location, date, relevant preferences and freshness, not just similar text. Approval state is not cached as an answer.
- Context compression must preserve user constraints and evidence; the baseline's four-turn window and payload length bounds are not presented as semantic compression.
- Only independent operations may run concurrently. Offline batching is distinct from interactive request latency.
- Approval is bound to an itinerary version. Changed content invalidates approval. Stale evidence requires revalidation and possibly renewed approval. Repeated approval/resume must not duplicate finalization.
- Human approval satisfies the chosen human-handoff demonstration. No claim of autonomous multi-agent handoff is made.
- Shared durable state and authenticated session ownership are mandatory before a cloud deployment. Do not simply remove the local guards and rely on ephemeral container SQLite.
- Record model/prompt/tool/workflow versions for later regression, drift and rollback lessons.

## Recording versions

Keep this ZIP as the saved Clip 2 starting version. Later, use version-control checkpoints for each teaching stage. Rehearse the complete advanced workflow before recording dependent clips, but show changes in their teaching order. Nothing needs to be deleted or deliberately broken to recreate a baseline.

The original outline document has not been edited. Its customer-support/refund examples and corresponding business metrics should be revised to match this scope; its production learning objectives remain.

## Provider contracts consulted

- https://openweathermap.org/api/geocoding-api
- https://old.openweathermap.org/forecast5
- https://docs.tavily.com/documentation/api-reference/endpoint/search
- https://docs.tavily.com/documentation/api-reference/endpoint/extract

The code calls these HTTP APIs directly through HTTPX, with schema-validated tool arguments and bounded responses. No additional agent framework is required for the baseline. Durable orchestration is introduced in M1 C6.
