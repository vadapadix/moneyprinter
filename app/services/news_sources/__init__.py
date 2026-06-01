from app.config import config
from app.models.schema import NewsQueryRequest, NewsStory


DEFAULT_AUTO_SOURCES = ["telethon", "newsdata", "guardian", "telegram"]


def get_provider(source: str):
    source = (source or "").lower().strip()
    if source == "newsdata":
        from app.services.news_sources.newsdata import NewsDataProvider

        return NewsDataProvider()
    if source == "guardian":
        from app.services.news_sources.guardian import GuardianProvider

        return GuardianProvider()
    if source == "telegram":
        from app.services.news_sources.telegram import TelegramProvider

        return TelegramProvider()
    if source == "telethon":
        from app.services.news_sources.telethon_source import TelethonProvider

        return TelethonProvider()
    return None


def _configured_auto_sources() -> list[str]:
    configured = config.app.get("news_auto_sources", DEFAULT_AUTO_SOURCES)
    if isinstance(configured, str):
        configured = [item.strip() for item in configured.split(",")]
    sources = []
    seen = set()
    for source in configured or []:
        source = str(source).strip().lower()
        if not source or source == "auto" or source in seen:
            continue
        seen.add(source)
        sources.append(source)
    return sources or DEFAULT_AUTO_SOURCES


def _story_identity(story: NewsStory) -> str:
    if story.url:
        return f"url:{story.url.strip().lower()}"
    return f"title:{story.provider.strip().lower()}:{story.title.strip().lower()}"


def _search_auto(query: NewsQueryRequest) -> list[NewsStory]:
    stories = []
    seen = set()
    per_source_limit = max(1, query.limit)
    for source in _configured_auto_sources():
        source_query = query.model_copy(update={"source": source, "limit": per_source_limit})
        for story in search(source, source_query):
            key = _story_identity(story)
            if key in seen:
                continue
            seen.add(key)
            stories.append(story)
            if len(stories) >= query.limit:
                return stories
    return stories


def search(source: str, query: NewsQueryRequest) -> list[NewsStory]:
    source = (source or query.source or "").lower().strip()
    if source in ("auto", "config"):
        return _search_auto(query)
    provider = get_provider(source)
    if not provider:
        return []
    return provider.search(query)
