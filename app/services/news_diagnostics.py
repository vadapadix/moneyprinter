import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from app.utils import utils


_LOCK = threading.Lock()


def _diag_dir() -> str:
    return utils.storage_dir("news/diagnostics", create=True)


def _path(task_id: str) -> str:
    safe_task_id = "".join(char for char in str(task_id) if char.isalnum() or char in "-_")
    return os.path.join(_diag_dir(), f"{safe_task_id}.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jsonable(value: Any):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump())
    return str(value)


def get_task_diagnostics(task_id: str) -> list[dict]:
    path = _path(task_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, list) else []
    except Exception as exc:
        logger.warning(f"failed to read news diagnostics for {task_id}: {exc}")
        return []


def record_event(task_id: str, event_name: str, **properties) -> None:
    if not task_id:
        return
    event = {
        "event": event_name,
        "created_at": _now(),
        "properties": _jsonable(properties),
    }
    with _LOCK:
        events = get_task_diagnostics(task_id)
        events.append(event)
        path = _path(task_id)
        temp_path = f"{path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(events, handle, ensure_ascii=False, indent=2)
        os.replace(temp_path, path)
