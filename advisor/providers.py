"""External data only. No invented fallback when a provider fails."""

from datetime import datetime, timedelta, timezone, date
import hashlib
import ipaddress
from urllib.parse import urlparse
import httpx


class ProviderFailure(Exception):
    def __init__(self, provider, code):
        self.provider, self.code = provider, code
        super().__init__(f"{provider}: {code}")


def safe_url(value):
    try:
        p = urlparse(value)
        if (
            p.scheme != "https"
            or not p.hostname
            or p.username
            or p.password
            or p.port not in (None, 443)
        ):
            return False
        if "." not in p.hostname or p.hostname.endswith(
            (".local", ".internal", ".localhost")
        ):
            return False
        try:
            if not ipaddress.ip_address(p.hostname).is_global:
                return False
        except ValueError:
            pass
        return len(value) < 2000
    except (TypeError, ValueError):
        return False


def location_id(row):
    return hashlib.sha256(
        f"{row['lat']},{row['lon']},{row['name']}".encode()
    ).hexdigest()[:12]


class Providers:
    def __init__(self, cfg, client=None):
        self.cfg = cfg
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(20, connect=5), follow_redirects=False
        )

    async def close(self):
        await self.client.aclose()

    async def request(self, provider, method, url, **kwargs):
        try:
            response = await self.client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            code = (
                "authentication"
                if status in (401, 403)
                else (
                    "quota_or_rate_limit"
                    if status in (429, 432, 433)
                    else "upstream_error"
                )
            )
            raise ProviderFailure(provider, code) from None
        except httpx.TimeoutException:
            raise ProviderFailure(provider, "timeout") from None
        except httpx.RequestError:
            raise ProviderFailure(provider, "connection") from None
        except ValueError:
            raise ProviderFailure(provider, "invalid_response") from None

    async def resolve(self, place):
        rows = await self.request(
            "OpenWeather",
            "GET",
            "https://api.openweathermap.org/geo/1.0/direct",
            params={"q": place, "limit": 5, "appid": self.cfg.weather_key},
        )
        if not isinstance(rows, list):
            raise ProviderFailure("OpenWeather", "invalid_response")
        locations = []
        for row in rows[:5]:
            if not all(k in row for k in ("name", "lat", "lon", "country")):
                continue
            locations.append(
                {
                    "id": location_id(row),
                    "name": row["name"],
                    "country": row["country"],
                    "region": row.get("state", ""),
                    "lat": row["lat"],
                    "lon": row["lon"],
                }
            )
        return {"locations": locations}

    async def forecast(self, location, day):
        requested = date.fromisoformat(day)
        data = await self.request(
            "OpenWeather",
            "GET",
            "https://api.openweathermap.org/data/2.5/forecast",
            params={
                "lat": location["lat"],
                "lon": location["lon"],
                "units": "metric",
                "appid": self.cfg.weather_key,
            },
        )
        if not isinstance(data, dict) or not data.get("list"):
            raise ProviderFailure("OpenWeather", "invalid_response")
        offset = int(data.get("city", {}).get("timezone", 0))
        tz = timezone(timedelta(seconds=offset))
        slots = []
        available = set()
        for row in data["list"]:
            local = datetime.fromtimestamp(row["dt"], tz)
            available.add(local.date().isoformat())
            if local.date() == requested:
                slots.append(
                    {
                        "local_time": local.isoformat(),
                        "temperature_c": row["main"]["temp"],
                        "conditions": row.get("weather", [{}])[0].get(
                            "description", "unknown"
                        ),
                        "rain_probability": row.get("pop"),
                        "wind_m_s": row.get("wind", {}).get("speed"),
                    }
                )
        common = {
            "location": location["name"],
            "location_id": location["id"],
            "date": day,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "provider": "OpenWeather",
            "available_dates": sorted(available),
            "timezone_offset_seconds": offset,
        }
        if not slots:
            return {
                **common,
                "error": "date_outside_forecast",
                "message": "No forecast slots cover the requested local date. Offer a provisional plan without weather claims or ask for a date in the returned range.",
            }
        return {
            **common,
            "slots": slots,
            "note": "3-hour forecast intervals; only returned intervals are covered. Times include the provider UTC offset.",
        }

    async def search(self, query):
        data = await self.request(
            "Tavily",
            "POST",
            "https://api.tavily.com/search",
            headers={"Authorization": "Bearer " + self.cfg.tavily_key},
            json={
                "query": query,
                "search_depth": "basic",
                "max_results": 5,
                "include_answer": False,
                "include_raw_content": False,
                "include_usage": True,
            },
        )
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise ProviderFailure("Tavily", "invalid_response")
        return {
            "results": [
                {
                    "title": str(r.get("title", "Source"))[:200],
                    "url": r["url"],
                    "excerpt": str(r.get("content", ""))[:2400],
                }
                for r in data["results"][:5]
                if safe_url(r.get("url"))
            ],
            "usage": data.get("usage", {}),
        }

    async def extract(self, urls):
        data = await self.request(
            "Tavily",
            "POST",
            "https://api.tavily.com/extract",
            headers={"Authorization": "Bearer " + self.cfg.tavily_key},
            json={
                "urls": urls,
                "extract_depth": "basic",
                "format": "text",
                "include_usage": True,
            },
        )
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise ProviderFailure("Tavily", "invalid_response")
        return {
            "results": [
                {"url": r["url"], "text": str(r.get("raw_content", ""))[:6000]}
                for r in data["results"]
                if r.get("url") in urls
            ],
            "failed_urls": [
                r.get("url")
                for r in data.get("failed_results", [])
                if r.get("url") in urls
            ],
            "usage": data.get("usage", {}),
        }
