import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

from core.config import settings

logger = logging.getLogger(__name__)

COST_FILE = str(Path(settings.storage_path) / "cost_stats.json")
PRICE_PER_1M = 0.30


def _load() -> dict:
    path = Path(COST_FILE)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"days": {}, "total": {"prompt": 0, "completion": 0, "cost": 0.0}}
    return {"days": {}, "total": {"prompt": 0, "completion": 0, "cost": 0.0}}


def _save(data: dict):
    Path(COST_FILE).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def record(prompt_tokens: int, completion_tokens: int):
    data = _load()
    today = str(date.today())
    day = data["days"].setdefault(today, {"prompt": 0, "completion": 0, "cost": 0.0})  # type: ignore
    total_tokens = prompt_tokens + completion_tokens
    cost = total_tokens / 1_000_000 * PRICE_PER_1M

    day["prompt"] += prompt_tokens
    day["completion"] += completion_tokens
    day["cost"] = round(day["cost"] + cost, 6)

    data["total"]["prompt"] += prompt_tokens
    data["total"]["completion"] += completion_tokens
    data["total"]["cost"] = round(data["total"]["cost"] + cost, 6)

    _save(data)


def stats() -> dict[str, Any]:
    return _load()
