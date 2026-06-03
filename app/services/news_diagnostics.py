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


def _event_properties(event: dict) -> dict:
    properties = event.get("properties", {})
    return properties if isinstance(properties, dict) else {}


def _count_skipped_relevance(attempts: list) -> int:
    if not isinstance(attempts, list):
        return 0
    return len(
        [
            attempt
            for attempt in attempts
            if isinstance(attempt, dict) and attempt.get("skipped_relevance")
        ]
    )


def media_summary_from_events(events: list[dict]) -> dict:
    stages = {
        "direct_news_media": {
            "stage": "direct_news_media",
            "source": "news_assets",
            "attempted": False,
            "downloaded_count": 0,
            "paths": [],
        },
        "related_telegram": {
            "stage": "related_telegram",
            "source": "telethon",
            "attempted": False,
            "downloaded_count": 0,
            "paths": [],
        },
        "yt_dlp": {
            "stage": "yt_dlp",
            "source": "yt-dlp",
            "attempted": False,
            "downloaded_count": 0,
            "paths": [],
            "attempt_count": 0,
            "skipped_relevance_count": 0,
        },
        "stock_fallback": {
            "stage": "stock_fallback",
            "source": "",
            "attempted": False,
            "downloaded_count": 0,
            "paths": [],
        },
    }
    required_clip_count = 0
    total_video_count = 0

    for event in events or []:
        event_name = event.get("event")
        properties = _event_properties(event)
        if event_name == "news_direct_media_ready":
            stage = stages["direct_news_media"]
            stage["attempted"] = True
            stage["downloaded_count"] = int(properties.get("direct_video_count") or 0)
            stage["source"] = properties.get("source") or stage["source"]
            required_clip_count = max(
                required_clip_count, int(properties.get("required_clip_count") or 0)
            )
            total_video_count = max(total_video_count, stage["downloaded_count"])
        elif event_name == "news_related_telegram_search_started":
            stage = stages["related_telegram"]
            stage["attempted"] = True
            stage["query"] = properties.get("query") or ""
            stage["requested_count"] = int(properties.get("requested_count") or 0)
            total_video_count = max(
                total_video_count, int(properties.get("existing_video_count") or 0)
            )
        elif event_name == "news_related_telegram_search_completed":
            stage = stages["related_telegram"]
            stage["attempted"] = True
            stage["downloaded_count"] = int(properties.get("downloaded_count") or 0)
            stage["paths"] = properties.get("downloaded_paths") or []
            total_video_count = max(
                total_video_count, int(properties.get("total_video_count") or 0)
            )
        elif event_name == "news_ytdlp_search_started":
            stage = stages["yt_dlp"]
            stage["attempted"] = True
            stage["query"] = properties.get("query") or ""
            stage["requested_count"] = int(properties.get("requested_count") or 0)
            total_video_count = max(
                total_video_count,
                int(properties.get("existing_direct_video_count") or 0),
            )
        elif event_name == "news_ytdlp_search_completed":
            stage = stages["yt_dlp"]
            attempts = properties.get("attempts") or []
            stage["attempted"] = True
            stage["downloaded_count"] = int(properties.get("downloaded_count") or 0)
            stage["paths"] = properties.get("downloaded_paths") or []
            stage["attempt_count"] = len(attempts) if isinstance(attempts, list) else 0
            stage["skipped_relevance_count"] = _count_skipped_relevance(attempts)
            total_video_count = max(
                total_video_count, int(properties.get("total_video_count") or 0)
            )
        elif event_name == "news_stock_fallback_started":
            stage = stages["stock_fallback"]
            stage["attempted"] = True
            stage["source"] = properties.get("source") or stage["source"]
            stage["search_terms"] = properties.get("search_terms") or []
            total_video_count = max(
                total_video_count, int(properties.get("existing_video_count") or 0)
            )
        elif event_name == "news_stock_fallback_completed":
            stage = stages["stock_fallback"]
            stage["attempted"] = True
            stage["source"] = properties.get("source") or stage["source"]
            stage["downloaded_count"] = int(properties.get("downloaded_count") or 0)
            total_video_count = max(
                total_video_count, int(properties.get("total_video_count") or 0)
            )

    stage_list = [stage for stage in stages.values() if stage["attempted"]]
    non_stock_count = sum(
        stage["downloaded_count"] for stage in stage_list if stage["stage"] != "stock_fallback"
    )
    used_sources = [
        stage["source"]
        for stage in stage_list
        if stage["downloaded_count"] > 0 and stage.get("source")
    ]
    stock_fallback_used = any(
        stage["stage"] == "stock_fallback" and stage["attempted"] for stage in stage_list
    )
    if not total_video_count:
        total_video_count = sum(stage["downloaded_count"] for stage in stage_list)
    if non_stock_count:
        status = "news_media_ready"
    elif total_video_count:
        status = "stock_fallback_only" if stock_fallback_used else "media_ready"
    else:
        status = "no_media"

    return {
        "status": status,
        "total_video_count": total_video_count,
        "non_stock_video_count": non_stock_count,
        "stock_fallback_used": stock_fallback_used,
        "used_sources": used_sources,
        "required_clip_count": required_clip_count,
        "stages": stage_list,
    }


def get_media_summary(task_id: str) -> dict:
    return media_summary_from_events(get_task_diagnostics(task_id))


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
