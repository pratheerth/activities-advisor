from dataclasses import dataclass, field
from pathlib import Path
import os
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)


@dataclass
class Settings:
    mode: str = field(default_factory=lambda: os.getenv("APP_MODE", "live"))
    model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4.1"))
    openai_key: str = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", ""), repr=False
    )
    weather_key: str = field(
        default_factory=lambda: os.getenv("OPENWEATHER_API_KEY", ""), repr=False
    )
    tavily_key: str = field(
        default_factory=lambda: os.getenv("TAVILY_API_KEY", ""), repr=False
    )
    database: str = field(
        default_factory=lambda: os.getenv(
            "ADVISOR_DB", str(ROOT / "runtime" / "advisor.db")
        )
    )
    max_tool_calls: int = 10
    max_model_calls: int = 12
    history_turns: int = 4
    run_timeout: float = 150

    def validate(self):
        if self.mode not in {"live", "demo"}:
            raise ValueError("APP_MODE must be live or demo")
        if self.mode == "live":
            missing = [
                name
                for name, value in [
                    ("OPENAI_API_KEY", self.openai_key),
                    ("OPENWEATHER_API_KEY", self.weather_key),
                    ("TAVILY_API_KEY", self.tavily_key),
                ]
                if not value or value.startswith("replace-")
            ]
            if missing:
                raise ValueError("Set these values in .env: " + ", ".join(missing))
        if os.getenv("K_SERVICE"):
            raise ValueError(
                "This is the local Clip 2 baseline. Configure external state and deployment authentication in Clip 3 before deploying it."
            )
