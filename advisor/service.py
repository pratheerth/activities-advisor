"""Bounded tool loop with streamed facts, not a scripted plan or hidden reasoning."""

import asyncio
from datetime import datetime, timezone
import json
import time
import uuid
from pydantic import ValidationError
from .schemas import Answer, TOOL_MODELS
from .providers import ProviderFailure

LABELS = {
    "resolve_location": "Resolve location · OpenWeather",
    "get_weather_forecast": "Check forecast · OpenWeather",
    "search_activities": "Search activities · Tavily",
    "read_activity_details": "Read venue details · Tavily",
}


class Agent:
    def __init__(self, cfg, store, model, providers):
        self.cfg, self.store, self.model, self.providers = cfg, store, model, providers

    async def execute_tool(self, name, args, state):
        if name == "resolve_location":
            result = await self.providers.resolve(args["place"])
            for location in result["locations"]:
                state["locations"][location["id"]] = location
            # A bounded registry is local memory, not semantic context compression.
            state["locations"] = dict(list(state["locations"].items())[-20:])
            return result
        if name == "get_weather_forecast":
            location = state["locations"].get(args["location_id"])
            if not location:
                return {
                    "error": "unknown_location",
                    "message": "Resolve the location first.",
                }
            result = await self.providers.forecast(location, args["date"])
            state["weather"] = result
            return result
        if name == "search_activities":
            result = await self.providers.search(args["query"])
            rows = []
            for row in result["results"]:
                existing = next(
                    (
                        sid
                        for sid, s in state["sources"].items()
                        if s["url"] == row["url"]
                    ),
                    None,
                )
                sid = existing or f"S{state['next_source']}"
                if not existing:
                    state["next_source"] += 1
                row = {
                    **row,
                    "id": sid,
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                }
                state["sources"][sid] = row
                rows.append(row)
            state["sources"] = dict(list(state["sources"].items())[-40:])
            return {"sources": rows, "usage": result.get("usage", {})}
        if name == "read_activity_details":
            ids = args["source_ids"]
            if any(sid not in state["sources"] for sid in ids):
                return {
                    "error": "unknown_source",
                    "message": "Use source IDs returned by search_activities.",
                }
            by_url = {state["sources"][sid]["url"]: sid for sid in ids}
            result = await self.providers.extract(list(by_url))
            return {
                "pages": [
                    {"source_id": by_url[row["url"]], "text": row["text"]}
                    for row in result["results"]
                ],
                "failed_source_ids": [by_url[url] for url in result["failed_urls"]],
                "usage": result.get("usage", {}),
            }
        return {"error": "unknown_tool"}

    async def stream(self, cid, owner, message, history, state, lease):
        rid = str(uuid.uuid4())
        events = []
        started = time.monotonic()
        messages = [m for turn in history[-self.cfg.history_turns :] for m in turn]
        offset = len(messages)
        messages.append({"role": "user", "content": message})
        answer = None
        seen = set()
        tool_count = 0
        used_sources = []

        def event(kind, **data):
            item = {
                "type": kind,
                "elapsed_ms": round((time.monotonic() - started) * 1000),
                **data,
            }
            events.append(item)
            return item

        try:
            yield event("started", run_id=rid, conversation_id=cid, mode=self.cfg.mode)
            try:
                async with asyncio.timeout(self.cfg.run_timeout):
                    for _ in range(self.cfg.max_model_calls):
                        yield event(
                            "thinking",
                            label="Considering the request and available evidence",
                        )
                        reply = await self.model.complete(messages, state)
                        event(
                            "model_call",
                            model=(
                                self.cfg.model
                                if self.cfg.mode == "live"
                                else "demo-fixture"
                            ),
                            usage=reply.get("usage", {}),
                        )
                        name = reply.get("tool")
                        if not name:
                            answer = Answer.model_validate_json(
                                reply["content"]
                            ).model_dump()
                            if answer["itinerary"]:
                                plan = answer["itinerary"]
                                # Enforce citation provenance. Semantic correctness is evaluated separately.
                                if (
                                    not plan["activities"]
                                    or len(plan["activities"]) > 6
                                ):
                                    raise ValueError("invalid_activity_count")
                                for activity in plan["activities"]:
                                    ids = activity["source_ids"]
                                    if not ids or any(
                                        sid not in state["sources"] for sid in ids
                                    ):
                                        raise ValueError("unsupported_source_reference")
                                    used_sources.extend(ids)
                                datetime.strptime(plan["date"], "%Y-%m-%d")
                            break
                        tool_count += 1
                        if tool_count > self.cfg.max_tool_calls:
                            raise ValueError("tool_budget_exceeded")
                        call_id = reply.get("call_id") or str(uuid.uuid4())
                        raw = reply.get("arguments") or {}
                        signature = json.dumps([name, raw], sort_keys=True)
                        if signature in seen:
                            raise ValueError("repeated_tool_call")
                        seen.add(signature)
                        messages.append(
                            {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": call_id,
                                        "type": "function",
                                        "function": {
                                            "name": name,
                                            "arguments": json.dumps(raw),
                                        },
                                    }
                                ],
                            }
                        )
                        yield event(
                            "tool_started",
                            tool=name,
                            label=LABELS.get(name, "Unknown tool"),
                            arguments=raw,
                        )
                        try:
                            if name not in TOOL_MODELS:
                                result = {
                                    "error": "unknown_tool",
                                    "message": "Choose an available tool.",
                                }
                            else:
                                args = (
                                    TOOL_MODELS[name].model_validate(raw).model_dump()
                                )
                                result = await self.execute_tool(name, args, state)
                        except (ValidationError, ValueError):
                            result = {
                                "error": "invalid_arguments",
                                "message": "Check the arguments, including date format, and correct them.",
                            }
                        except ProviderFailure as exc:
                            result = {
                                "error": exc.code,
                                "provider": exc.provider,
                                "message": "This provider did not return usable data. Explain the limitation; do not invent results.",
                            }
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call_id,
                                "content": json.dumps(result),
                            }
                        )
                        yield event(
                            "tool_finished",
                            tool=name,
                            label=LABELS.get(name, name),
                            result=result,
                            ok="error" not in result,
                        )
                    if answer is None:
                        raise ValueError("model_budget_exceeded")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Never emit exception strings: HTTP errors can contain API keys in URLs.
                code = type(exc).__name__
                safe_reason = (
                    str(exc)
                    if isinstance(exc, ValueError)
                    and str(exc)
                    in {
                        "tool_budget_exceeded",
                        "model_budget_exceeded",
                        "repeated_tool_call",
                        "unsupported_source_reference",
                        "invalid_activity_count",
                        "model_output_incomplete",
                        "model_refusal",
                    }
                    else code
                )
                yield event(
                    "run_error",
                    code=safe_reason,
                    label="The request could not be completed",
                )
                answer = {
                    "status": "error",
                    "message": "I couldn’t finish this request. Please try again or narrow it down. Any itinerary already on screen is the previous version; no new plan was completed.",
                    "itinerary": None,
                }
                if isinstance(exc, TimeoutError):
                    answer["message"] = (
                        "This request took too long. Please try a simpler request. No new plan was completed."
                    )
                if code in {"AuthenticationError", "PermissionDeniedError"}:
                    answer["message"] = (
                        "The model connection was rejected. Check the OpenAI API key and model access in .env, then restart the server."
                    )
                if code == "RateLimitError":
                    answer["message"] = (
                        "The model provider reported a usage limit. Check API credits and rate limits, then try again."
                    )
            # Complete any interrupted tool-call pair so later turns have valid history.
            if messages[-1].get("tool_calls"):
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": messages[-1]["tool_calls"][0]["id"],
                        "content": json.dumps({"error": "interrupted"}),
                    }
                )
            messages.append({"role": "assistant", "content": json.dumps(answer)})
            result = {
                **answer,
                "run_id": rid,
                "conversation_id": cid,
                "mode": self.cfg.mode,
                "sources": [
                    state["sources"][sid]
                    for sid in dict.fromkeys(used_sources)
                    if sid in state["sources"]
                ],
                "weather": (
                    state["weather"]
                    if answer.get("itinerary")
                    and state["weather"]
                    and state["weather"].get("date") == answer["itinerary"]["date"]
                    and state["weather"].get("location", "").lower()
                    in answer["itinerary"]["location"].lower()
                    else None
                ),
            }
            event("run_finished", status=result["status"], tool_calls=tool_count)
            self.store.finish(
                cid,
                owner,
                lease,
                (history + [messages[offset:]])[-self.cfg.history_turns :],
                state,
                result,
                events,
            )
            yield {"type": "result", **result}
        finally:
            self.store.release(cid, lease)
