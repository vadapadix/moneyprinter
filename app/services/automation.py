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
from app.services import news_pipeline, news_sources, trends
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
                "platforms": [platform.value for platform in request.platforms],
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


def build_video_params_from_news(
    request: NewsAutomationRunRequest, story: NewsStory
) -> VideoParams:
    source_context = news_pipeline.build_source_context(story)
    platforms = request.platforms or _configured_platforms()
    auto_publish = (
        bool(config.app.get("social_auto_publish", False))
        if request.auto_publish is None
        else request.auto_publish
    )
    return VideoParams(
        video_subject=story.title,
        video_script=f"{story.title}\n\n{story.summary}".strip(),
        video_language=request.video_language or request.language or story.language or "",
        video_aspect="9:16",
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
        paragraph_number=1,
        social_auto_publish=auto_publish,
        social_platforms=platforms,
        social_privacy=request.privacy or _configured_privacy(),
        tiktok_direct_post_consent=request.tiktok_direct_post_consent,
    )


def prepare_news_run(request: NewsAutomationRunRequest) -> dict:
    run_id = utils.get_uuid()
    source = (
        config.app.get("news_source", "newsdata")
        if request.source in ("", "config")
        else request.source
    )
    query = NewsQueryRequest(
        source=source,
        query=request.query or config.app.get("news_query", ""),
        country=request.country or config.app.get("news_country", "us"),
        language=request.language or config.app.get("news_language", "en"),
        category=request.category or config.app.get("news_category") or None,
        limit=request.limit,
    )
    stories = news_sources.search(source, query)
    tasks = []
    for story in stories[: request.limit]:
        task_id = utils.get_uuid()
        params = build_video_params_from_news(request, story)
        tasks.append(
            {
                "task_id": task_id,
                "params": params,
                "story": story,
                "auto_publish": params.social_auto_publish,
                "platforms": [
                    platform.value for platform in (params.social_platforms or [])
                ],
            }
        )

    return {
        "run_id": run_id,
        "query": query,
        "stories": stories,
        "tasks": tasks,
    }
