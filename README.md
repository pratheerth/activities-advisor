# Activities Advisor — Clip 2 baseline

A conversational activities agent with a web UI. In **live mode**, an OpenAI model chooses from four tools backed by **OpenWeather geocoding and forecasts**, **Tavily Search**, and **Tavily Extract**. It proposes a source-linked itinerary and revises it through conversation.

This replaces the customer-support teaching direction. It is a separate project; keep the older folders as references if useful. The locked scope and every later clip's extension are recorded in `docs/SCOPE.md`.

## 1. Set up on your Mac

Extract the ZIP and open a terminal inside the `activities-advisor` folder. Use Python 3.12 or newer; the package was tested on Python 3.12. A separate environment avoids carrying over the support agent's configuration.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
cp .env.example .env
```

If your `python3` is already Python 3.12 or newer, use `python3` in the first command. All commands below run from this project folder with its virtual environment active.

Open `.env` in your editor and enter your three keys:

```dotenv
APP_MODE=live
OPENAI_API_KEY=your-openai-key
OPENAI_MODEL=gpt-4.1
OPENWEATHER_API_KEY=your-openweather-key
TAVILY_API_KEY=your-tavily-key
```

The app loads this file automatically. Do not paste these keys into the UI or share them. Existing exported environment variables take precedence over `.env`; if changing the file seems to have no effect, open a fresh terminal and activate this environment. Restart the server after configuration changes.

Provider account pages:

- OpenAI: https://platform.openai.com/api-keys — API billing is separate from a ChatGPT subscription.
- OpenWeather: https://home.openweathermap.org/api_keys — use a key with access to geocoding and the 5-day / 3-hour forecast endpoint. This app does not use One Call.
- Tavily: https://app.tavily.com/ — the same key is used for Search and Extract.

The default model matches the earlier working setup. It must support tool calling and strict structured outputs. Model routing and model comparison are later lessons.

## 2. Start the UI

Stop another server using port 8000, or choose a different port.

```bash
python -m uvicorn advisor.api:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. The top-right badge should say **Live tools**. No customer token is needed. This local version uses a browser session cookie to isolate conversations.

The left side holds your request and follow-ups. The right side shows the itinerary, weather summary, source links, and **actual tool activity streamed as calls start and finish**. Expand an activity to inspect the tool's arguments and result. The activity panel shows the latest turn; completed traces remain available through Run details.

## 3. Try this conversation

First:

> Plan a relaxed afternoon in Edinburgh, Scotland tomorrow. I like museums and architecture. Keep costs low and include an indoor option if it rains. Please check the venue details.

Then:

> Make it less walking, with no more than two main stops. Keep the same city, date and interests.

Check that the agent retains the city/date/preferences, uses actual tool results, and revises the plan. Its exact tool sequence and wording may vary. Read the sources before recording: source links establish where evidence came from; they do not automatically prove the recommendation is correct.

Use **New trip** between independent examples. A page reload starts a new chat in this simple UI. The server retains completed conversation/run records, but there is no conversation-history browser yet. Only four recent complete exchanges are sent to the model.

See `docs/CLIP-2-REHEARSAL.md` for the short screen sequence and acceptance checks.

## 4. Run the live rehearsal check

In another terminal, activate this environment and run:

```bash
python -m advisor.check --out reports/live-rehearsal.json
```

It makes real API calls when `APP_MODE=live`. It uses an isolated database and sends one initial request plus one revision. It checks structure, tool execution, and basic revision requirements. **Read the saved responses and evidence as well**; a passing smoke check is not a general LLM-quality evaluation.

If something fails, share the generated report after checking it for anything personal. The application does not put provider keys in that report. The UI's Run details also opens a completed request trace containing the model's tool calls and results, not private chain-of-thought.

## Offline UI preview

To inspect the UI without keys, stop the live server and run:

```bash
APP_MODE=demo python -m uvicorn advisor.api:app --host 127.0.0.1 --port 8000
```

This is an explicitly labelled **Edinburgh fixture**, not a live agent. It returns a fixed sample and a simple revision regardless of the real-world request. No external tools or LLM are called. Do not use it as evidence of real language understanding or as a live-provider course demonstration.

```bash
python -m pytest tests -q
APP_MODE=demo python -m advisor.check --out reports/demo-rehearsal.json
```

## Troubleshooting

- **Startup names missing keys:** replace placeholders in `.env`; restart. Live mode never silently switches to demo.
- **OpenWeather authentication failure:** confirm key activation and access to the two endpoints used here. A newly created key may not be usable immediately.
- **Tavily quota/rate limit:** check your account's available usage. No fabricated search results are substituted.
- **Model usage limit:** check API credits and rate limits. Keys alone do not provide billing credit.
- **No forecast for a date:** only returned forecast intervals are available. The agent should offer a provisional itinerary or ask for another date. No current-weather substitution.
- **A source cannot be extracted:** the result records failed sources; the agent should explain remaining uncertainty or find another source within its call budget.
- **Run interrupted:** provider timeouts, the run time budget, or repeated tool calls may stop a request. Inspect the trace and retry. Earlier itineraries are labelled as previous versions when an update fails.

## Baseline boundary

Included: web UI, four real tools, one model, structured itinerary output, recent conversation context, local SQLite storage, source provenance checks, tool activity, bounded execution and failure reporting.

Not yet included: deployment, routing, semantic caching, semantic context compression, parallel tool execution, provider batch jobs, human approval, durable paused execution, dashboards, automated alerts, drift analysis, or rollback automation. Tests and simple traces support development; later clips make the corresponding production practices explicit.

This app deliberately starts on loopback, accepts local hosts only, and refuses a Cloud Run environment until Clip 3 adds external state and deployment authentication. Do not expose it publicly as-is. A local SQLite conversation saved between turns is **not** a durable checkpoint of an interrupted run.

## Project map

| File | Responsibility |
|---|---|
| `advisor/api.py` | FastAPI, local session boundary, streaming HTTP endpoint |
| `advisor/service.py` | Model/tool loop, activity events, source validation |
| `advisor/model.py` | Instructions and the real model adapter |
| `advisor/providers.py` | OpenWeather and Tavily HTTP adapters |
| `advisor/schemas.py` | Four tool contracts and structured itinerary |
| `advisor/store.py` | Local conversation and run storage |
| `advisor/web/` | Responsive planner UI; no frontend build step |
| `advisor/demo.py` | Clearly separated offline fixtures |
| `advisor/check.py` | Two-turn live/demo rehearsal command |
| `tests/` | Mocked provider, model, API and conversation checks |
| `docs/SCOPE.md` | Locked scope and future clip mapping |

Dependency versions are pinned. `requirements.txt` lists direct dependencies; `requirements.lock` also pins their transitive dependencies. No keys or runtime conversations are shipped in the ZIP.
# activities-advisor
