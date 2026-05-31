from app.config import config
from app.models.schema import MaterialInfo, NewsMediaAsset, NewsQueryRequest, NewsStory
from app.services import news_sources
from app.services.news_sources.base import is_direct_video_url, media_asset_to_material


def build_materials_from_story(story: NewsStory) -> list[MaterialInfo]:
    materials = []
    for asset in story.media:
        if asset.media_type == "video" and is_direct_video_url(asset.url):
            materials.append(media_asset_to_material(asset))
    return materials


def build_materials_from_assets(assets: list[dict]) -> list[MaterialInfo]:
    story = NewsStory(media=[NewsMediaAsset(**asset) for asset in assets])
    return build_materials_from_story(story)


def build_source_context(story: NewsStory) -> dict:
    return {
        "provider": story.provider,
        "title": story.title,
        "summary": story.summary,
        "source_url": story.url,
        "published_at": story.published_at,
        "language": story.language,
        "country": story.country,
        "category": story.category,
        "keywords": story.keywords,
        "media": [asset.model_dump() for asset in story.media],
    }


def query_from_params(params) -> NewsQueryRequest:
    return NewsQueryRequest(
        source=params.news_source or config.app.get("news_source", "newsdata"),
        query=params.news_query or params.video_subject,
        country=params.news_country or config.app.get("news_country", "us"),
        language=params.news_language
        or params.video_language
        or config.app.get("news_language", "en"),
        category=params.news_category or config.app.get("news_category") or None,
        limit=1,
    )


def prepare_news_context(params) -> NewsStory | None:
    if params.video_source != "news":
        return None

    query = query_from_params(params)
    stories = news_sources.search(query.source, query)
    if not stories:
        return None

    story = stories[0]
    params.news_source = query.source
    params.news_query = query.query
    params.news_source_context = build_source_context(story)
    params.news_media_assets = [asset.model_dump() for asset in story.media]
    params.trend_context = {
        "source": story.provider,
        "topic": story.title,
        "url": story.url,
        "published_at": story.published_at,
        "keywords": story.keywords,
    }

    if story.title:
        params.video_subject = story.title
    if not params.video_script and (story.title or story.summary):
        params.video_script = f"{story.title}\n\n{story.summary}".strip()

    return story
