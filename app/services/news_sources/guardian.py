import re

import requests
from loguru import logger

from app.config import config
from app.models.schema import NewsMediaAsset, NewsQueryRequest, NewsStory


def _strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value or "").strip()


class GuardianProvider:
    source_name = "guardian"
    API_URL = "https://content.guardianapis.com/search"

    def search(self, query: NewsQueryRequest) -> list[NewsStory]:
        api_key = config.app.get("guardian_api_key", "").strip()
        if not api_key:
            logger.warning("guardian_api_key is not configured")
            return []

        params = {
            "api-key": api_key,
            "q": query.query,
            "page-size": min(max(query.limit, 1), 50),
            "show-fields": "thumbnail,trailText,shortUrl",
        }
        if query.category:
            params["section"] = query.category

        try:
            response = requests.get(self.API_URL, params=params, timeout=(15, 45))
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.RequestException as exc:
            logger.error(f"failed to fetch Guardian stories: {str(exc)}")
            return []

        stories = []
        for item in payload.get("response", {}).get("results", []):
            title = item.get("webTitle") or ""
            url = item.get("webUrl") or ""
            if not title:
                continue

            fields = item.get("fields") or {}
            media = []
            thumbnail = fields.get("thumbnail") or ""
            if thumbnail:
                media.append(
                    NewsMediaAsset(
                        provider=self.source_name,
                        url=thumbnail,
                        media_type="image",
                        title=title,
                        credit="The Guardian",
                        source_url=url,
                    )
                )

            stories.append(
                NewsStory(
                    provider=self.source_name,
                    title=title,
                    summary=_strip_html(fields.get("trailText") or ""),
                    url=url,
                    published_at=item.get("webPublicationDate") or "",
                    language=query.language,
                    country=query.country,
                    category=item.get("sectionName") or item.get("sectionId") or "",
                    keywords=[item.get("sectionName") or item.get("sectionId") or ""],
                    media=media,
                )
            )
        return stories
