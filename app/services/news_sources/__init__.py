from app.models.schema import NewsQueryRequest, NewsStory


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
    return None


def search(source: str, query: NewsQueryRequest) -> list[NewsStory]:
    provider = get_provider(source)
    if not provider:
        return []
    return provider.search(query)
