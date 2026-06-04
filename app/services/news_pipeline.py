from app.config import config
from app.models.schema import MaterialInfo, NewsMediaAsset, NewsQueryRequest, NewsStory
from app.services import news_sources, web_media
from app.services.news_sources.base import is_direct_video_url, media_asset_to_material


def build_materials_from_story(story: NewsStory) -> list[MaterialInfo]:
    materials = []
    for asset in story.media:
        if asset.media_type == "video" and is_direct_video_url(asset.url):
            materials.append(media_asset_to_material(asset))
    return materials


def enrich_story_media(story: NewsStory) -> NewsStory:
    if not config.app.get("news_web_media_enabled", True):
        return story

    existing_urls = {asset.url for asset in story.media}
    discovered = [
        asset for asset in web_media.discover_story_media(story)
        if asset.url not in existing_urls
    ]
    if discovered:
        story.media = [*story.media, *discovered]
    return story


def build_materials_from_assets(assets: list[dict]) -> list[MaterialInfo]:
    story = NewsStory(media=[NewsMediaAsset(**asset) for asset in assets])
    return build_materials_from_story(story)


def discover_related_telegram_video_materials(
    query: str,
    limit: int = 2,
) -> list[MaterialInfo]:
    if not config.app.get("news_related_telegram_video_enabled", True):
        return []

    query = (query or "").strip()
    if not query or limit <= 0:
        return []

    search_limit = max(
        limit,
        int(config.app.get("news_related_telegram_video_search_limit", limit)),
    )
    stories = news_sources.search(
        "telethon",
        NewsQueryRequest(
            source="telethon",
            query=query,
            limit=search_limit,
            language=config.app.get("news_language", "en"),
        ),
    )

    materials = []
    seen = set()
    for story in stories:
        for material in build_materials_from_story(story):
            if material.url in seen:
                continue
            seen.add(material.url)
            materials.append(material)
            if len(materials) >= limit:
                return materials
    return materials


def build_source_context(story: NewsStory) -> dict:
    source_urls = []
    for url in [
        story.url,
        *web_media.extract_urls(story.summary),
        *[asset.source_url for asset in story.media],
        *[asset.url for asset in story.media],
    ]:
        cleaned = (url or "").strip()
        if cleaned and cleaned not in source_urls:
            source_urls.append(cleaned)

    return {
        "provider": story.provider,
        "title": story.title,
        "summary": story.summary,
        "source_url": story.url,
        "source_urls": source_urls,
        "published_at": story.published_at,
        "language": story.language,
        "country": story.country,
        "category": story.category,
        "keywords": story.keywords,
        "media": [asset.model_dump() for asset in story.media],
    }


def build_script_subject(story: NewsStory, output_language: str = "English") -> str:
    title = story.title.strip()
    summary = story.summary.strip()
    source_url = story.url.strip()
    return (
        f"Write a short factual news voiceover in {output_language}. "
        "The headline is the angle of the story, so the script must stay directly on that headline. "
        "Use only facts found in the source material below. Do not invent names, numbers, causes, reactions, or consequences. "
        "Aim for 160-220 spoken words with enough substance for a detailed 45-60 second short, but if the source material is thin, keep the script shorter instead of padding it. "
        "Use plain human newsreader English with concrete details and short sentences. "
        "Avoid filler, motivational wording, broad lessons, vague phrases like 'this highlights' or 'raises questions', and any intro such as 'welcome'. "
        "Do not mention Telegram, the source URL, hashtags, markdown, narrator labels, or that this is a script. "
        "Make it suitable for a 45-60 second YouTube Shorts/TikTok news video. "
        f"Title: {title}. "
        f"Summary: {summary}. "
        f"Source URL: {source_url}."
    ).strip()


def story_from_source_context(source_context: dict) -> NewsStory:
    media = source_context.get("media") or []
    return NewsStory(
        provider=source_context.get("provider", ""),
        title=source_context.get("title", ""),
        summary=source_context.get("summary", ""),
        url=source_context.get("source_url", ""),
        published_at=source_context.get("published_at", ""),
        language=source_context.get("language", ""),
        country=source_context.get("country", ""),
        category=source_context.get("category", ""),
        keywords=source_context.get("keywords", []),
        media=[NewsMediaAsset(**asset) for asset in media],
    )


def query_from_params(params) -> NewsQueryRequest:
    return NewsQueryRequest(
        source=params.news_source or config.app.get("news_source", "auto"),
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

    if params.news_source_context:
        story = story_from_source_context(params.news_source_context)
        story = enrich_story_media(story)
        params.news_media_assets = params.news_media_assets or [
            asset.model_dump() for asset in story.media
        ]
        params.trend_context = {
            "source": story.provider,
            "topic": story.title,
            "url": story.url,
            "published_at": story.published_at,
            "keywords": story.keywords,
        }
        if story.title:
            params.video_subject = build_script_subject(story)
        return story

    query = query_from_params(params)
    stories = news_sources.search(query.source, query)
    if not stories:
        return None

    story = enrich_story_media(stories[0])
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
        params.video_subject = build_script_subject(story)

    return story
