import hashlib
import json
import os
import re
import threading
from datetime import datetime, timezone
from typing import Iterable

from loguru import logger

from app.models.schema import NewsStory
from app.utils import utils


_LOCK = threading.Lock()


def _history_path() -> str:
    return os.path.join(utils.storage_dir("news", create=True), "history.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _title_signature(value: str) -> str:
    normalized = re.sub(r"[^0-9a-z]+", " ", _normalize_text(value)).strip()
    if len(normalized) < 18:
        return ""
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"title:{digest}"


def _story_signatures(story: NewsStory) -> set[str]:
    signatures = {story_key(story)}
    title_signature = _title_signature(story.title)
    if title_signature:
        signatures.add(title_signature)
    return signatures


def story_key(story: NewsStory) -> str:
    if story.url:
        return f"url:{story.url.strip().lower()}"
    raw = "|".join(
        [
            _normalize_text(story.provider),
            _normalize_text(story.title),
            _normalize_text(story.published_at),
        ]
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"story:{digest}"


def _load_unlocked() -> dict:
    path = _history_path()
    if not os.path.exists(path):
        return {"stories": {}}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict) and isinstance(data.get("stories"), dict):
            return data
    except Exception as exc:
        logger.warning(f"failed to read news history, starting fresh: {exc}")
    return {"stories": {}}


def _save_unlocked(data: dict) -> None:
    path = _history_path()
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


def load_history() -> dict:
    with _LOCK:
        return _load_unlocked()


def is_seen(story: NewsStory) -> bool:
    signatures = _story_signatures(story)
    with _LOCK:
        history = _load_unlocked().get("stories", {})
        return any(signature in history for signature in signatures)


def filter_new_stories(stories: Iterable[NewsStory], limit: int) -> list[NewsStory]:
    selected = []
    seen_in_batch = set()
    with _LOCK:
        history = _load_unlocked().get("stories", {})
        for story in stories:
            signatures = _story_signatures(story)
            if signatures.intersection(history) or signatures.intersection(seen_in_batch):
                continue
            seen_in_batch.update(signatures)
            selected.append(story)
            if len(selected) >= limit:
                break
    return selected


def reserve_story(story: NewsStory, run_id: str = "", task_id: str = "") -> str:
    key = story_key(story)
    with _LOCK:
        history = _load_unlocked()
        stories = history.setdefault("stories", {})
        entry = {
            **stories.get(key, {}),
            "status": "reserved",
            "provider": story.provider,
            "title": story.title,
            "url": story.url,
            "run_id": run_id,
            "task_id": task_id,
            "reserved_at": _now(),
        }
        stories[key] = entry
        title_signature = _title_signature(story.title)
        if title_signature:
            stories[title_signature] = {
                **stories.get(title_signature, {}),
                **entry,
                "alias_for": key,
            }
        _save_unlocked(history)
    return key


def mark_story_result(
    story: NewsStory,
    task_id: str = "",
    success: bool = False,
    videos: list[str] | None = None,
    publish_results: list[dict] | None = None,
) -> None:
    key = story_key(story)
    with _LOCK:
        history = _load_unlocked()
        stories = history.setdefault("stories", {})
        current = stories.get(key, {})
        entry = {
            **current,
            "status": "completed" if success else "failed",
            "provider": story.provider or current.get("provider", ""),
            "title": story.title or current.get("title", ""),
            "url": story.url or current.get("url", ""),
            "task_id": task_id or current.get("task_id", ""),
            "completed_at": _now(),
            "video_count": len(videos or []),
            "publish_count": len(publish_results or []),
        }
        stories[key] = entry
        title_signature = _title_signature(story.title)
        if title_signature:
            stories[title_signature] = {
                **stories.get(title_signature, {}),
                **entry,
                "alias_for": key,
            }
        _save_unlocked(history)
