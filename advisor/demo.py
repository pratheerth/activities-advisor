"""Explicit offline fixture. No real model or weather/search calls; not a recording mode."""

from datetime import date, timedelta
import json


class DemoProviders:
    async def close(self):
        pass

    async def resolve(self, place):
        return {
            "locations": [
                {
                    "id": "edinburgh-demo",
                    "name": "Edinburgh",
                    "country": "GB",
                    "region": "Scotland",
                    "lat": 55.9533,
                    "lon": -3.1883,
                }
            ]
        }

    async def forecast(self, location, day):
        return {
            "provider": "OFFLINE FIXTURE",
            "location": "Edinburgh",
            "location_id": location["id"],
            "date": day,
            "slots": [
                {
                    "local_time": day + "T12:00:00+01:00",
                    "temperature_c": 14,
                    "conditions": "light rain (fixture)",
                    "rain_probability": 0.7,
                    "wind_m_s": 4,
                }
            ],
            "note": "Illustrative test weather. Not a forecast.",
        }

    async def search(self, query):
        return {
            "results": [
                {
                    "title": "National Museum of Scotland · fixture",
                    "url": "https://www.nms.ac.uk/national-museum-of-scotland",
                    "excerpt": "Fixture: indoor museum; general admission free. Check official details before visiting.",
                },
                {
                    "title": "Scottish National Gallery · fixture",
                    "url": "https://www.nationalgalleries.org/visit/scottish-national-gallery",
                    "excerpt": "Fixture: indoor art gallery; general collection free. Check official details.",
                },
                {
                    "title": "Edinburgh visitor information · fixture",
                    "url": "https://edinburgh.org/",
                    "excerpt": "Fixture: visitor information about Edinburgh.",
                },
            ],
            "usage": {},
        }

    async def extract(self, urls):
        return {
            "results": [
                {
                    "url": url,
                    "text": "OFFLINE FIXTURE: indoor cultural attraction. Confirm current opening hours and special-exhibition charges on the official website.",
                }
                for url in urls
            ],
            "failed_urls": [],
            "usage": {},
        }


class DemoModel:
    async def close(self):
        pass

    async def complete(self, messages, state):
        last = max(i for i, m in enumerate(messages) if m["role"] == "user")
        current = messages[last:]
        used = [
            m["tool_calls"][0]["function"]["name"]
            for m in current
            if m.get("tool_calls")
        ]

        def call(name, args):
            return {
                "tool": name,
                "arguments": args,
                "call_id": "demo-" + str(len(used)),
                "usage": {},
            }

        if not used:
            return call("resolve_location", {"place": "Edinburgh, GB"})
        if len(used) == 1:
            return call(
                "get_weather_forecast",
                {
                    "location_id": "edinburgh-demo",
                    "date": (date.today() + timedelta(days=1)).isoformat(),
                },
            )
        if len(used) == 2:
            return call(
                "search_activities",
                {"query": "Edinburgh indoor free activities official museum gallery"},
            )
        if len(used) == 3:
            return call(
                "read_activity_details", {"source_ids": list(state["sources"])[:2]}
            )
        revised = last > 0
        plan = {
            "title": (
                "A slower afternoon in Edinburgh"
                if revised
                else "An Edinburgh afternoon, rain or shine"
            ),
            "location": "Edinburgh",
            "date": state["weather"]["date"],
            "weather_summary": "Illustrative light rain, 14°C. This is an offline fixture, not real weather.",
            "activities": [
                {
                    "time": "13:00",
                    "title": "National Museum of Scotland",
                    "details": "Explore the indoor galleries at your own pace. This is illustrative content for testing the UI.",
                    "cost_note": "Fixture: general admission free; verify before visiting.",
                    "source_ids": ["S1"],
                },
                {
                    "time": "15:00",
                    "title": "Scottish National Gallery",
                    "details": "An indoor alternative. Allow a break and consider transport between venues; walking distance has not been verified.",
                    "cost_note": "Fixture: check exhibition charges.",
                    "source_ids": ["S2"],
                },
                {
                    "time": "16:30",
                    "title": "A flexible break",
                    "details": "Leave time for a rest rather than adding another attraction. Choose somewhere nearby on the day.",
                    "cost_note": "Refreshments extra; no price verified.",
                    "source_ids": ["S3"],
                },
            ],
            "caveats": [
                "Offline fixture: no external API calls or live language understanding.",
                "No tickets booked. Check current details before visiting.",
            ],
        }
        if revised:
            plan["activities"] = plan["activities"][:2]
        return {
            "tool": None,
            "content": json.dumps(
                {
                    "status": "limited",
                    "message": (
                        "This is the offline Edinburgh fixture. Switch APP_MODE to live to plan real trips."
                        if not revised
                        else "Here is the fixture revision, with fewer stops. Live mode is needed for real conversational planning."
                    ),
                    "itinerary": plan,
                }
            ),
            "usage": {},
        }
