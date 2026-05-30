from datetime import datetime, timezone

import requests
from loguru import logger

from app.config import config
from app.models.schema import TrendCandidate


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _manual_trends(region: str = "", limit: int = 5) -> list[TrendCandidate]:
    seeds = config.app.get("trend_manual_topics", [])
    if isinstance(seeds, str):
        seeds = [topic.strip() for topic in seeds.split(",")]

    candidates = []
    for index, topic in enumerate(seeds[:limit]):
        if not topic:
            continue
        candidates.append(
            TrendCandidate(
                source="manual",
                topic=topic,
                title=topic,
                score=float(limit - index),
                region=region,
                fetched_at=_now_iso(),
            )
        )
    return candidates


def _youtube_trends(
    region: str = "US", category_id: str | None = None, limit: int = 5
) -> list[TrendCandidate]:
    api_key = config.app.get("youtube_data_api_key", "")
    if not api_key:
        logger.warning("youtube_data_api_key is not configured; returning no trends")
        return []

    params = {
        "part": "snippet,statistics",
        "chart": "mostPopular",
        "regionCode": region,
        "maxResults": min(max(limit, 1), 50),
        "key": api_key,
    }
    if category_id:
        params["videoCategoryId"] = category_id

    try:
        response = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params=params,
            timeout=(15, 45),
        )
        response.raise_for_status()
        payload = response.json()
    except requests.exceptions.RequestException as exc:
        logger.error(f"failed to fetch YouTube trends: {str(exc)}")
        return []

    candidates = []
    for item in payload.get("items", []):
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        title = snippet.get("title", "")
        video_id = item.get("id", "")
        try:
            score = float(stats.get("viewCount", 0))
        except (TypeError, ValueError):
            score = 0.0
        if title:
            candidates.append(
                TrendCandidate(
                    source="youtube",
                    topic=title,
                    title=title,
                    url=f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
                    score=score,
                    region=region,
                    tags=snippet.get("tags", [])[:10],
                    fetched_at=_now_iso(),
                )
            )
    return candidates


def discover_trends(
    source: str = "manual",
    region: str = "US",
    category_id: str | None = None,
    limit: int = 5,
) -> list[TrendCandidate]:
    source = (source or "manual").lower()
    if source == "youtube":
        return _youtube_trends(region=region, category_id=category_id, limit=limit)
    if source == "manual":
        return _manual_trends(region=region, limit=limit)
    logger.warning(f"unsupported trend source: {source}")
    return []
