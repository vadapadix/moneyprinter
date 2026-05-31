import requests
from loguru import logger

from app.config import config
from app.models.schema import NewsMediaAsset, NewsQueryRequest, NewsStory


class NewsDataProvider:
    source_name = "newsdata"
    API_URL = "https://newsdata.io/api/1/latest"

    def search(self, query: NewsQueryRequest) -> list[NewsStory]:
        api_key = config.app.get("newsdata_api_key", "").strip()
        if not api_key:
            logger.warning("newsdata_api_key is not configured")
            return []

        params = {
            "apikey": api_key,
            "q": query.query,
            "country": query.country,
            "language": query.language,
            "size": min(max(query.limit, 1), 10),
        }
        if query.category:
            params["category"] = query.category

        try:
            response = requests.get(self.API_URL, params=params, timeout=(15, 45))
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.RequestException as exc:
            logger.error(f"failed to fetch NewsData stories: {str(exc)}")
            return []

        stories = []
        for item in payload.get("results", []):
            title = item.get("title") or ""
            link = item.get("link") or ""
            if not title:
                continue

            media = []
            image_url = item.get("image_url") or ""
            if image_url:
                media.append(
                    NewsMediaAsset(
                        provider=self.source_name,
                        url=image_url,
                        media_type="image",
                        title=title,
                        credit=item.get("source_id") or "",
                        source_url=link,
                    )
                )

            stories.append(
                NewsStory(
                    provider=self.source_name,
                    title=title,
                    summary=item.get("description") or item.get("content") or "",
                    url=link,
                    published_at=item.get("pubDate") or "",
                    language=item.get("language") or "",
                    country=",".join(item.get("country") or []),
                    category=",".join(item.get("category") or []),
                    keywords=item.get("keywords") or [],
                    media=media,
                )
            )
        return stories
