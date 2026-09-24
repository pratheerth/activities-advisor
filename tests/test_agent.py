import asyncio
import json
from datetime import datetime, timezone
import httpx
import pytest
from fastapi.testclient import TestClient
from openai import AsyncOpenAI
from advisor.api import create_app
from advisor.config import Settings
from advisor.demo import DemoModel, DemoProviders
from advisor.model import Model
from advisor.providers import Providers, ProviderFailure, safe_url
from advisor.schemas import TOOLS
from advisor.service import Agent
from advisor.store import Store, Busy, Missing


@pytest.fixture
def cfg(tmp_path):
    return Settings(mode="demo", database=str(tmp_path / "advisor.db"))


class Scripted:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    async def close(self):
        pass

    async def complete(self, messages, state):
        self.calls.append(json.loads(json.dumps(messages)))
        result = next(self.replies)
        if isinstance(result, Exception):
            raise result
        return result


def answer(message="Which city?", status="needs_information", itinerary=None):
    return {
        "tool": None,
        "content": json.dumps(
            {"status": status, "message": message, "itinerary": itinerary}
        ),
    }


def call(name, **args):
    return {"tool": name, "arguments": args, "call_id": "test-call"}


def events(client, message, cid=None):
    r = client.post("/api/chat", json={"message": message, "conversation_id": cid})
    assert r.status_code == 200, r.text
    return [json.loads(line) for line in r.text.splitlines()]


def test_streams_four_tools_before_final_plan(cfg):
    with TestClient(create_app(cfg)) as c:
        c.get("/")
        e = events(c, "Plan an afternoon in Edinburgh tomorrow")
        assert e[0]["type"] == "started"
        assert [x["tool"] for x in e if x["type"] == "tool_finished"] == list(
            t["function"]["name"] for t in TOOLS
        )
        r = e[-1]
        assert (
            r["type"] == "result"
            and r["mode"] == "demo"
            and len(r["itinerary"]["activities"]) == 3
        )
        trace = c.get("/api/runs/" + r["run_id"]).json()
        assert trace["events"][-1]["type"] == "run_finished"
        assert len([x for x in trace["events"] if x["type"] == "model_call"]) == 5
        assert c.get("/static/app.js").status_code == 200
        assert "script-src" in c.get("/").headers["content-security-policy"]


def test_demo_revision_and_new_trip(cfg):
    with TestClient(create_app(cfg)) as c:
        c.get("/")
        first = events(c, "Edinburgh")[-1]
        second = events(c, "Less walking please", first["conversation_id"])[-1]
        assert second["conversation_id"] == first["conversation_id"]
        assert len(second["itinerary"]["activities"]) == 2
        fresh = events(c, "Edinburgh")[-1]
        assert (
            fresh["conversation_id"] != first["conversation_id"]
            and len(fresh["itinerary"]["activities"]) == 3
        )


def test_followup_history_reaches_model(cfg):
    m = Scripted(
        [
            answer(),
            answer("Which Springfield do you mean?"),
            answer("I can help with Springfield, Illinois."),
        ]
    )
    with TestClient(create_app(cfg, model=m)) as c:
        c.get("/")
        r = events(c, "Plan a day for me")[-1]
        events(c, "Springfield", r["conversation_id"])
        events(c, "Illinois", r["conversation_id"])
        assert [x["content"] for x in m.calls[-1] if x["role"] == "user"] == [
            "Plan a day for me",
            "Springfield",
            "Illinois",
        ]
        assert any(
            "Which Springfield" in x.get("content", "")
            for x in m.calls[-1]
            if x["role"] == "assistant"
        )


def test_conversation_persists_across_restart(cfg):
    with TestClient(create_app(cfg, model=Scripted([answer()]))) as c:
        c.get("/")
        cookie = c.cookies.get("advisor_session")
        r = events(c, "Plan a day")[-1]
    m = Scripted([answer("Thanks for the city.")])
    with TestClient(create_app(cfg, model=m)) as c:
        c.cookies.set("advisor_session", cookie)
        events(c, "Edinburgh", r["conversation_id"])
        assert m.calls[0][0]["content"] == "Plan a day"


def test_sessions_cannot_read_each_other(cfg):
    with TestClient(create_app(cfg)) as a, TestClient(create_app(cfg)) as b:
        a.get("/")
        b.get("/")
        r = events(a, "Edinburgh")[-1]
        assert (
            b.post(
                "/api/chat",
                json={"message": "continue", "conversation_id": r["conversation_id"]},
            ).status_code
            == 404
        )
        assert b.get("/api/runs/" + r["run_id"]).status_code == 404


def test_api_rejects_forged_state_and_cross_origin(cfg):
    with TestClient(create_app(cfg)) as c:
        assert c.post("/api/chat", json={"message": "hello"}).status_code == 401
        c.get("/")
        assert (
            c.post("/api/chat", json={"message": "hello", "history": []}).status_code
            == 422
        )
        assert (
            c.post(
                "/api/chat",
                json={"message": "hello"},
                headers={"Origin": "https://attacker.example"},
            ).status_code
            == 403
        )
        assert c.get("/", headers={"Host": "attacker.example"}).status_code == 403
        assert c.post("/api/chat", json={"message": "   "}).status_code == 422


def test_concurrent_turn_lock(cfg):
    store = Store(cfg.database)
    cid = store.create("a")
    _, _, lease = store.acquire(cid, "a")
    with pytest.raises(Busy):
        store.acquire(cid, "a")
    store.release(cid, lease)
    store.acquire(cid, "a")


def test_no_invented_coordinates_or_unseen_extraction(cfg):
    m = Scripted(
        [
            call("get_weather_forecast", location_id="invented", date="2026-09-23"),
            call("read_activity_details", source_ids=["S999"]),
            answer("Please supply a location."),
        ]
    )
    with TestClient(create_app(cfg, model=m)) as c:
        c.get("/")
        e = events(c, "Help")
        assert [x["result"]["error"] for x in e if x["type"] == "tool_finished"] == [
            "unknown_location",
            "unknown_source",
        ]


def test_provider_failure_is_passed_to_model(cfg):
    class Broken(DemoProviders):
        async def search(self, query):
            raise ProviderFailure("Tavily", "quota_or_rate_limit")

    m = Scripted(
        [
            call("search_activities", query="Edinburgh"),
            answer("Search is unavailable.", status="limited"),
        ]
    )
    with TestClient(create_app(cfg, model=m, providers=Broken())) as c:
        c.get("/")
        e = events(c, "Edinburgh")
        assert e[-1]["status"] == "limited" and e[-1]["itinerary"] is None
        assert json.loads(m.calls[-1][-1]["content"])["error"] == "quota_or_rate_limit"


def test_model_errors_do_not_leak_keys(cfg):
    with TestClient(
        create_app(cfg, model=Scripted([RuntimeError("secret-key-in-url")]))
    ) as c:
        c.get("/")
        e = events(c, "hello")
        assert e[-1]["status"] == "error"
        assert "secret-key" not in json.dumps(e)
        trace = c.get("/api/runs/" + e[-1]["run_id"]).text
        assert "secret-key" not in trace


def test_duplicate_tool_call_stops_loop(cfg):
    m = Scripted(
        [
            call("resolve_location", place="Edinburgh"),
            call("resolve_location", place="Edinburgh"),
        ]
    )
    with TestClient(create_app(cfg, model=m)) as c:
        c.get("/")
        e = events(c, "Edinburgh")
        assert len([x for x in e if x["type"] == "tool_finished"]) == 1
        assert any(x.get("code") == "repeated_tool_call" for x in e)


def test_timeout_releases_conversation(cfg):
    class Slow:
        async def close(self):
            pass

        async def complete(self, messages, state):
            await asyncio.sleep(0.1)

    cfg.run_timeout = 0.01
    with TestClient(create_app(cfg, model=Slow())) as c:
        c.get("/")
        r = events(c, "hello")[-1]
        assert r["status"] == "error" and "too long" in r["message"]
        store = c.app.state.agent.store
        _, _, lease = store.acquire(
            r["conversation_id"], c.cookies.get("advisor_session")
        )
        store.release(r["conversation_id"], lease)


def test_history_is_bounded_and_tool_pairs_complete(cfg):
    with TestClient(create_app(cfg)) as c:
        c.get("/")
        cid = None
        for _ in range(6):
            cid = events(c, "Edinburgh", cid)[-1]["conversation_id"]
        store = c.app.state.agent.store
        history, _, lease = store.acquire(cid, c.cookies.get("advisor_session"))
        assert len(history) == 4
        for turn in history:
            assert turn[0]["role"] == "user" and turn[-1]["role"] == "assistant"
            assert [tc["id"] for x in turn for tc in x.get("tool_calls", [])] == [
                x["tool_call_id"] for x in turn if x["role"] == "tool"
            ]
        store.release(cid, lease)


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "http://example.com",
        "https://127.0.0.1",
        "https://localhost",
        "https://user:pass@example.com",
        "https://example.com:8000",
    ],
)
def test_unsafe_source_urls_rejected(url):
    assert not safe_url(url)


def test_provider_contracts_and_local_forecast_date(cfg):
    captured = []

    def handler(req):
        captured.append(req)
        if req.url.path.endswith("/direct"):
            return httpx.Response(
                200,
                json=[{"name": "Tokyo", "country": "JP", "lat": 35.6, "lon": 139.7}],
            )
        if req.url.path.endswith("/forecast"):
            stamp = int(datetime(2026, 9, 22, 18, tzinfo=timezone.utc).timestamp())
            return httpx.Response(
                200,
                json={
                    "city": {"timezone": 32400},
                    "list": [
                        {
                            "dt": stamp,
                            "main": {"temp": 21},
                            "weather": [{"description": "clear"}],
                            "pop": 0,
                            "wind": {"speed": 2},
                        }
                    ],
                },
            )
        if req.url.path == "/search":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "title": "Venue",
                            "url": "https://example.com/venue",
                            "content": "Details",
                        },
                        {"url": "javascript:alert(1)"},
                    ],
                    "usage": {"credits": 1},
                },
            )
        return httpx.Response(
            200,
            json={
                "results": [
                    {"url": "https://example.com/venue", "raw_content": "Hours: 10–17"}
                ],
                "failed_results": [],
            },
        )

    async def check():
        p = Providers(cfg, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        loc = (await p.resolve("Tokyo"))["locations"][0]
        forecast = await p.forecast(loc, "2026-09-23")
        assert forecast["slots"][0]["local_time"] == "2026-09-23T03:00:00+09:00"
        missing = await p.forecast(loc, "2026-09-24")
        assert missing["error"] == "date_outside_forecast"
        search = await p.search("Tokyo museum")
        assert len(search["results"]) == 1
        assert (await p.extract(["https://example.com/venue"]))["results"][0][
            "text"
        ] == "Hours: 10–17"
        await p.close()

    asyncio.run(check())
    assert captured[0].url.params["limit"] == "5"
    assert captured[1].url.params["units"] == "metric"
    assert json.loads(captured[-2].content)["include_answer"] is False
    assert json.loads(captured[-1].content)["format"] == "text"


@pytest.mark.parametrize(
    "status,code",
    [(401, "authentication"), (429, "quota_or_rate_limit"), (500, "upstream_error")],
)
def test_provider_errors_sanitized(cfg, status, code):
    async def check():
        p = Providers(
            cfg,
            httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda r: httpx.Response(status, json={"error": "secret"})
                )
            ),
        )
        with pytest.raises(ProviderFailure) as caught:
            await p.resolve("Edinburgh")
        assert caught.value.code == code and "secret" not in str(caught.value)
        await p.close()

    asyncio.run(check())


def test_live_model_http_payload_without_credentials(cfg):
    captured = []

    def handler(req):
        captured.append(json.loads(req.content))
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 1,
                "model": cfg.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "tool1",
                                    "type": "function",
                                    "function": {
                                        "name": "resolve_location",
                                        "arguments": '{"place":"Edinburgh"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 10,
                    "total_tokens": 30,
                },
            },
        )

    async def check():
        client = AsyncOpenAI(
            api_key="test-only",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        m = Model(cfg, client)
        reply = await m.complete(
            [{"role": "user", "content": "Edinburgh"}], {"locations": {}, "sources": {}}
        )
        assert reply["tool"] == "resolve_location"
        assert reply["arguments"] == {"place": "Edinburgh"}
        await m.close()

    asyncio.run(check())
    assert captured[0]["response_format"]["json_schema"]["strict"] is True
    assert captured[0]["parallel_tool_calls"] is False
    assert len(captured[0]["tools"]) == 4


def test_unseen_citations_blocked(cfg):
    plan = {
        "title": "Bad plan",
        "location": "Edinburgh",
        "date": "2026-09-23",
        "weather_summary": "Unknown",
        "activities": [
            {
                "time": "13:00",
                "title": "Invented",
                "details": "Unknown",
                "cost_note": "Unknown",
                "source_ids": ["S999"],
            }
        ],
        "caveats": [],
    }
    with TestClient(
        create_app(
            cfg, model=Scripted([answer("Here", status="answered", itinerary=plan)])
        )
    ) as c:
        c.get("/")
        r = events(c, "plan")[-1]
        assert r["status"] == "error" and r["itinerary"] is None


def test_live_configuration_requires_all_keys(cfg):
    cfg.mode = "live"
    cfg.openai_key = cfg.weather_key = cfg.tavily_key = ""
    with pytest.raises(ValueError, match="OPENWEATHER_API_KEY"):
        cfg.validate()
