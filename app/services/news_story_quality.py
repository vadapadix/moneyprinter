from dataclasses import dataclass
from datetime import datetime, timezone

from app.models.schema import NewsStory
from app.services.news_sources.base import is_direct_video_url


@dataclass(frozen=True)
class StoryQuality:
    story: NewsStory
    score: int
    reasons: list[str]


def _parse_datetime(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    for candidate in (normalized, normalized.replace(" ", "T")):
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            continue
    return None


def score_story(story: NewsStory) -> StoryQuality:
    score = 0
    reasons = []
    title = (story.title or "").strip()
    summary = (story.summary or "").strip()

    if len(title) >= 18:
        score += 20
        reasons.append("clear_headline")
    elif len(title) >= 8:
        score += 8
        reasons.append("short_headline")
    else:
        score -= 30
        reasons.append("weak_or_missing_headline")

    if len(summary) >= 180:
        score += 25
        reasons.append("detailed_summary")
    elif len(summary) >= 60:
        score += 14
        reasons.append("usable_summary")
    elif summary:
        score += 4
        reasons.append("thin_summary")
    else:
        score -= 14
        reasons.append("missing_summary")

    if story.url:
        score += 10
        reasons.append("source_url_present")
    else:
        score -= 8
        reasons.append("missing_source_url")

    direct_videos = [
        asset
        for asset in story.media
        if asset.media_type == "video" and is_direct_video_url(asset.url)
    ]
    videos = [asset for asset in story.media if asset.media_type == "video"]
    images = [asset for asset in story.media if asset.media_type == "image"]
    if direct_videos:
        score += 30
        reasons.append("direct_video_media")
    elif videos:
        score += 18
        reasons.append("video_media")
    elif images:
        score += 8
        reasons.append("image_media")

    if story.keywords:
        score += min(len(story.keywords), 5)
        reasons.append("keywords_present")

    published_at = _parse_datetime(story.published_at)
    if published_at:
        age_hours = (datetime.now(timezone.utc) - published_at).total_seconds() / 3600
        if age_hours <= 24:
            score += 12
            reasons.append("fresh_under_24h")
        elif age_hours <= 72:
            score += 6
            reasons.append("recent_under_72h")
        else:
            score -= 4
            reasons.append("older_story")

    return StoryQuality(story=story, score=score, reasons=reasons)


def rank_stories(stories: list[NewsStory]) -> list[StoryQuality]:
    scored = [score_story(story) for story in stories]
    return sorted(scored, key=lambda item: item.score, reverse=True)
