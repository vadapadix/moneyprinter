from datetime import datetime, timezone

import requests
from loguru import logger

from app.config import config
from app.models.schema import NewsQueryRequest, NewsStory


def _configured_channel_ids() -> set[str]:
    channel_ids = config.app.get("telegram_channel_ids", [])
    if isinstance(channel_ids, str):
        channel_ids = [value.strip() for value in channel_ids.split(",")]
    return {str(value).strip() for value in channel_ids if str(value).strip()}


def _message_text(message: dict) -> str:
    return (message.get("text") or message.get("caption") or "").strip()


class TelegramProvider:
    source_name = "telegram"

    def search(self, query: NewsQueryRequest) -> list[NewsStory]:
        token = config.app.get("telegram_bot_token", "").strip()
        allowed_channel_ids = _configured_channel_ids()
        if not token:
            logger.warning("telegram_bot_token is not configured")
            return []
        if not allowed_channel_ids:
            logger.warning("telegram_channel_ids is not configured")
            return []

        params = {
            "limit": min(max(int(config.app.get("telegram_max_messages", 20)), 1), 100),
            "allowed_updates": '["channel_post"]',
        }
        try:
            response = requests.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params=params,
                timeout=(15, 45),
            )
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.RequestException as exc:
            logger.error(f"failed to fetch Telegram updates: {str(exc)}")
            return []

        if not payload.get("ok", False):
            logger.error(f"Telegram getUpdates failed: {payload}")
            return []

        needle = (query.query or "").lower().strip()
        stories = []
        for update in payload.get("result", []):
            message = update.get("channel_post") or {}
            chat = message.get("chat") or {}
            chat_id = str(chat.get("id") or "").strip()
            if chat_id not in allowed_channel_ids:
                continue

            text = _message_text(message)
            if not text:
                continue
            if needle and needle not in text.lower():
                continue

            title = text.splitlines()[0][:120].strip()
            published_at = ""
            if message.get("date"):
                published_at = datetime.fromtimestamp(
                    int(message["date"]), tz=timezone.utc
                ).isoformat()

            stories.append(
                NewsStory(
                    provider=self.source_name,
                    title=title,
                    summary=text,
                    url="",
                    published_at=published_at,
                    language=query.language,
                    country=query.country,
                    category=query.category or "",
                    keywords=[query.query] if query.query else [],
                )
            )
            if len(stories) >= query.limit:
                break

        return stories
