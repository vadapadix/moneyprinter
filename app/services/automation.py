from app.config import config
from app.models.schema import (
    AutomationRunRequest,
    NewsAutomationRunRequest,
    NewsQueryRequest,
    NewsStory,
    PublishPrivacy,
    SocialPlatform,
    VideoParams,
)
from app.services import (
    news_diagnostics,
    news_history,
    news_pipeline,
    news_sources,
    news_story_quality,
    trends,
)
from app.services.social_platform_utils import platform_values
from app.utils import utils


def build_video_params_from_trend(request: AutomationRunRequest, topic: str) -> VideoParams:
    return VideoParams(
        video_subject=topic,
        video_language=request.video_language or "",
        video_aspect="9:16",
        paragraph_number=1,
        social_auto_publish=request.auto_publish,
        social_platforms=request.platforms,
    )


def prepare_run(request: AutomationRunRequest) -> dict:
    run_id = utils.get_uuid()
    candidates = trends.discover_trends(
        source=request.trend_source,
        region=request.region,
        category_id=request.category_id,
        limit=request.limit,
    )
    tasks = []
    for candidate in candidates[: request.limit]:
        task_id = utils.get_uuid()
        params = build_video_params_from_trend(request, candidate.topic)
        tasks.append(
            {
                "task_id": task_id,
                "params": params,
                "trend": candidate,
                "auto_publish": request.auto_publish,
                "platforms": platform_values(request.platforms),
            }
        )

    return {
        "run_id": run_id,
        "candidates": candidates,
        "tasks": tasks,
    }


def _configured_platforms() -> list[SocialPlatform]:
    platforms = config.app.get("social_platforms", ["youtube", "tiktok"])
    values = []
    for platform in platforms:
        try:
            values.append(SocialPlatform(platform))
        except ValueError:
            continue
    return values or [SocialPlatform.youtube, SocialPlatform.tiktok]


def _configured_privacy() -> PublishPrivacy:
    try:
        return PublishPrivacy(config.app.get("social_privacy", "private"))
    except ValueError:
        return PublishPrivacy.private


def _news_output_language(request: NewsAutomationRunRequest) -> str:
    return (
        request.video_language
        or config.app.get("news_output_language", "")
        or config.app.get("video_language", "")
        or "en"
    )


def _configured_voice_name() -> str:
    return (
        config.ui.get("voice_name", "")
        or config.app.get("voice_name", "")
        or "en-US-BrianNeural-Male"
    )


def _news_bgm_type() -> str:
    return str(config.app.get("news_bgm_type", "news_serious") or "news_serious")


def _news_bgm_volume() -> float:
    return float(config.app.get("news_bgm_volume", 0.08))


def build_video_params_from_news(
    request: NewsAutomationRunRequest, story: NewsStory
) -> VideoParams:
    story = news_pipeline.enrich_story_media(story)
    source_context = news_pipeline.build_source_context(story)
    output_language = _news_output_language(request)
    platforms = request.platforms or _configured_platforms()
    auto_publish = (
        bool(config.app.get("social_auto_publish", False))
        if request.auto_publish is None
        else request.auto_publish
    )
    return VideoParams(
        video_subject=news_pipeline.build_script_subject(story),
        video_script="",
        video_language=output_language,
        video_aspect="9:16",
        video_clip_duration=int(config.app.get("news_video_clip_duration", 5)),
        video_source="news",
        news_source=story.provider or request.source,
        news_query=request.query or story.title,
        news_country=request.country or story.country,
        news_language=request.language or story.language,
        news_category=request.category or story.category or None,
        news_source_context=source_context,
        news_media_assets=[asset.model_dump() for asset in story.media],
        trend_context={
            "source": story.provider,
            "topic": story.title,
            "url": story.url,
            "published_at": story.published_at,
            "keywords": story.keywords,
        },
        paragraph_number=int(config.app.get("news_script_paragraphs", 3)),
        voice_name=_configured_voice_name(),
        voice_rate=float(
            config.app.get("news_voice_rate", 1.42)
        ),
        bgm_type=_news_bgm_type(),
        bgm_volume=_news_bgm_volume(),
        font_name=config.ui.get("font_name", config.app.get("font_name", "STHeitiMedium.ttc")),
        font_size=int(config.ui.get("font_size", config.app.get("font_size", 60))),
        subtitle_position=config.ui.get("subtitle_position", config.app.get("subtitle_position", "bottom")),
        social_auto_publish=auto_publish,
        social_platforms=platforms,
        social_privacy=request.privacy or _configured_privacy(),
        tiktok_direct_post_consent=request.tiktok_direct_post_consent,
    )


def _unique_selection_attempts(
    source: str,
    query: NewsQueryRequest,
    requested_limit: int,
) -> tuple[list[NewsStory], list[dict], list[dict]]:
    requested_limit = max(1, requested_limit)
    base_multiplier = max(1, int(config.app.get("news_story_fetch_multiplier", 3)))
    max_multiplier = max(
        base_multiplier,
        int(config.app.get("news_unique_selection_max_fetch_multiplier", 12)),
    )

    stories_by_key: dict[str, NewsStory] = {}
    attempts = []
    selected_stories: list[NewsStory] = []
    multiplier = base_multiplier

    while multiplier <= max_multiplier:
        fetch_limit = max(requested_limit, requested_limit * multiplier)
        search_query = query.model_copy(update={"limit": fetch_limit})
        stories = news_sources.search(source, search_query)
        for story in stories:
            stories_by_key.setdefault(news_history.story_key(story), story)

        ranked_stories = news_story_quality.rank_stories(stories_by_key.values())
        selected_stories = news_history.filter_new_stories(
            [item.story for item in ranked_stories], requested_limit
        )
        attempts.append(
            {
                "fetch_limit": fetch_limit,
                "raw_found_count": len(stories),
                "unique_found_count": len(stories_by_key),
                "selected_count": len(selected_stories),
            }
        )

        if len(selected_stories) >= requested_limit:
            break
        multiplier *= 2

    ranked_payload = [
        {
            "story": item.story,
            "score": item.score,
            "reasons": item.reasons,
        }
        for item in news_story_quality.rank_stories(stories_by_key.values())
    ]
    return list(stories_by_key.values()), ranked_payload, attempts


def prepare_news_run(request: NewsAutomationRunRequest) -> dict:
    run_id = utils.get_uuid()
    requested_limit = max(1, request.limit)
    source = (
        config.app.get("news_source", "auto")
        if request.source in ("", "config")
        else request.source
    )
    query = NewsQueryRequest(
        source=source,
        query=request.query or config.app.get("news_query", ""),
        country=request.country or config.app.get("news_country", "us"),
        language=request.language or config.app.get("news_language", "en"),
        category=request.category or config.app.get("news_category") or None,
        limit=requested_limit,
    )
    stories, ranked_stories, selection_attempts = _unique_selection_attempts(
        source=source,
        query=query,
        requested_limit=requested_limit,
    )
    quality_by_url = {
        news_history.story_key(item["story"]): item
        for item in ranked_stories
    }
    selected_stories = [item["story"] for item in ranked_stories]
    selected_stories = news_history.filter_new_stories(selected_stories, requested_limit)
    tasks = []
    for index, story in enumerate(selected_stories):
        task_id = utils.get_uuid()
        news_history.reserve_story(story, run_id=run_id, task_id=task_id)
        params = build_video_params_from_news(request, story)
        quality = quality_by_url.get(news_history.story_key(story))
        news_diagnostics.record_event(
            task_id,
            "news_story_reserved",
            run_id=run_id,
            selected_index=index,
            total_found=len(stories),
            total_selected=len(selected_stories),
            selection_attempts=selection_attempts,
            provider=story.provider,
            title=story.title,
            url=story.url,
            media_asset_count=len(story.media),
            quality_score=quality["score"] if quality else None,
            quality_reasons=quality["reasons"] if quality else [],
            auto_publish=params.social_auto_publish,
            platforms=platform_values(params.social_platforms),
        )
        tasks.append(
            {
                "task_id": task_id,
                "params": params,
                "story": story,
                "auto_publish": params.social_auto_publish,
                "platforms": platform_values(params.social_platforms),
            }
        )

    return {
        "run_id": run_id,
        "query": query,
        "stories": stories,
        "ranked_stories": ranked_stories,
        "selection_attempts": selection_attempts,
        "selected_stories": selected_stories,
        "tasks": tasks,
    }
