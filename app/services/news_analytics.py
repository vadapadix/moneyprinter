from app.models import const


WEAK_TITLES = {"", "unknown", "untitled", "n/a", "na", "generated short video"}


def _as_list(value) -> list:
    return value if isinstance(value, list) else []


def _is_complete(item: dict) -> bool:
    return bool(item.get("success")) or item.get("state") == const.TASK_STATE_COMPLETE


def _is_failed(item: dict) -> bool:
    return item.get("state") == const.TASK_STATE_FAILED or item.get("success") is False


def _video_count(item: dict) -> int:
    return len(_as_list(item.get("videos")))


def _publish_results(item: dict) -> list[dict]:
    results = item.get("publish_results") or item.get("cross_post_results") or []
    return results if isinstance(results, list) else []


def _media_summary(item: dict) -> dict:
    summary = item.get("news_media_summary") or {}
    return summary if isinstance(summary, dict) else {}


def _metadata(item: dict) -> dict:
    metadata = item.get("social_metadata") or {}
    return metadata if isinstance(metadata, dict) else {}


def _publish_preflight(item: dict) -> dict:
    preflight = item.get("publish_preflight") or {}
    return preflight if isinstance(preflight, dict) else {}


def _platform_metrics(results: list[dict]) -> dict:
    platforms: dict[str, dict] = {}
    for result in results:
        if not isinstance(result, dict):
            continue
        platform = str(result.get("platform") or "unknown").lower()
        entry = platforms.setdefault(
            platform,
            {"attempts": 0, "success": 0, "failed": 0},
        )
        entry["attempts"] += 1
        if result.get("success"):
            entry["success"] += 1
        else:
            entry["failed"] += 1
    return platforms


def summarize_news_items(items: list[dict]) -> dict:
    publish_results = []
    for item in items or []:
        publish_results.extend(_publish_results(item))

    generated_video_count = sum(_video_count(item) for item in items or [])
    completed_count = len([item for item in items or [] if _is_complete(item)])
    failed_count = len([item for item in items or [] if _is_failed(item)])
    stock_fallback_task_count = len(
        [
            item
            for item in items or []
            if bool(_media_summary(item).get("stock_fallback_used"))
        ]
    )
    stock_only_task_count = len(
        [
            item
            for item in items or []
            if _media_summary(item).get("status") == "stock_fallback_only"
        ]
    )
    no_media_task_count = len(
        [item for item in items or [] if _media_summary(item).get("status") == "no_media"]
    )
    non_stock_video_count = sum(
        int(_media_summary(item).get("non_stock_video_count") or 0)
        for item in items or []
    )
    unknown_title_count = len(
        [
            item
            for item in items or []
            if str(_metadata(item).get("title") or "").strip().lower() in WEAK_TITLES
        ]
    )
    blocked_preflights = [
        _publish_preflight(item)
        for item in items or []
        if _publish_preflight(item).get("skip_reason")
    ]
    blocked_reasons: dict[str, int] = {}
    for preflight in blocked_preflights:
        reason = str(preflight.get("skip_reason") or "unknown")
        blocked_reasons[reason] = blocked_reasons.get(reason, 0) + 1
    successful_upload_count = len(
        [result for result in publish_results if isinstance(result, dict) and result.get("success")]
    )
    failed_upload_count = len(
        [
            result
            for result in publish_results
            if isinstance(result, dict) and not result.get("success")
        ]
    )

    return {
        "task_count": len(items or []),
        "completed_count": completed_count,
        "failed_count": failed_count,
        "generated_video_count": generated_video_count,
        "publish_attempt_count": len(publish_results),
        "publish_success_count": successful_upload_count,
        "publish_failed_count": failed_upload_count,
        "publish_blocked_task_count": len(blocked_preflights),
        "publish_blocked_reasons": blocked_reasons,
        "platforms": _platform_metrics(publish_results),
        "non_stock_video_count": non_stock_video_count,
        "stock_fallback_task_count": stock_fallback_task_count,
        "stock_only_task_count": stock_only_task_count,
        "no_media_task_count": no_media_task_count,
        "unknown_title_count": unknown_title_count,
        "generation_success_rate": round(completed_count / len(items), 4)
        if items
        else 0,
        "publish_success_rate": round(successful_upload_count / len(publish_results), 4)
        if publish_results
        else 0,
    }


def filter_news_tasks(tasks: list[dict]) -> list[dict]:
    return [
        task
        for task in tasks or []
        if isinstance(task, dict)
        and (
            task.get("news_story")
            or task.get("news_media_summary")
            or task.get("automation_run_id")
        )
    ]


def summarize_state_tasks(tasks: list[dict]) -> dict:
    news_tasks = filter_news_tasks(tasks)
    summary = summarize_news_items(news_tasks)
    summary["total_state_task_count"] = len(tasks or [])
    return summary
