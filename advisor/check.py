"""Run the Clip 2 conversation in an isolated database. Live mode incurs API usage."""

import argparse
import asyncio
from dataclasses import replace
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
from .config import Settings
from .store import Store
from .service import Agent
from .model import Model
from .providers import Providers
from .demo import DemoModel, DemoProviders


async def run(cfg):
    cfg.validate()
    with tempfile.TemporaryDirectory(prefix="advisor-check-") as directory:
        cfg = replace(cfg, database=str(Path(directory) / "check.db"))
        model = DemoModel() if cfg.mode == "demo" else Model(cfg)
        providers = DemoProviders() if cfg.mode == "demo" else Providers(cfg)
        store = Store(cfg.database)
        agent = Agent(cfg, store, model, providers)
        owner = "local-rehearsal"
        cid = store.create(owner)
        day = (date.today() + timedelta(days=1)).isoformat()
        messages = [
            f"Plan a relaxed afternoon in Edinburgh, Scotland on {day}. I like museums and architecture. Keep costs low, read relevant venue details, and include an indoor option if it rains.",
            "Make it less walking, with no more than two main stops. Keep the same city, date and interests.",
        ]
        turns = []
        try:
            for message in messages:
                history, state, lease = store.acquire(cid, owner)
                stream = [
                    e
                    async for e in agent.stream(
                        cid, owner, message, history, state, lease
                    )
                ]
                result = stream[-1]
                turns.append(
                    {
                        "request": message,
                        "result": result,
                        "events": store.run(result["run_id"], owner)["events"],
                    }
                )
        finally:
            await model.close()
            await providers.close()
        first, second = [turn["result"] for turn in turns]
        completed = {
            e["tool"]
            for e in turns[0]["events"]
            if e["type"] == "tool_finished" and e["ok"]
        }
        checks = {
            "initial_plan_returned": first.get("itinerary") is not None,
            "four_tools_completed": {
                "resolve_location",
                "get_weather_forecast",
                "search_activities",
                "read_activity_details",
            }
            <= completed,
            "revision_returned": second.get("itinerary") is not None,
            "same_conversation": first["conversation_id"] == second["conversation_id"],
            "same_date": bool(
                first.get("itinerary")
                and second.get("itinerary")
                and first["itinerary"]["date"] == second["itinerary"]["date"]
            ),
            "revision_at_most_two_stops": bool(
                second.get("itinerary") and len(second["itinerary"]["activities"]) <= 2
            ),
        }
        return {
            "mode": cfg.mode,
            "scope": "Local isolated two-turn smoke check. Structural checks only; not evidence of factual correctness, deployed reliability, or general conversational quality. Demo mode makes no external calls.",
            "passed": all(checks.values()),
            "checks": checks,
            "review_required": [
                "Weather date/location and forecast match the request.",
                "Sources actually support the selected activities and any hours or prices.",
                "The revision retains the budget/interests and meaningfully reduces walking.",
                "Tool failures and unknown facts are explained honestly.",
            ],
            "turns": turns,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="reports/rehearsal.json")
    args = parser.parse_args()
    report = asyncio.run(run(Settings()))
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2))
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in {"turns", "review_required"}},
            indent=2,
        )
    )
    print("Read the answers and source evidence in " + str(output))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
