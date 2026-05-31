import asyncio
import os
from datetime import timezone

from loguru import logger

from app.config import config
from app.models.schema import NewsMediaAsset, NewsQueryRequest, NewsStory
from app.utils import utils

try:
    from telethon import TelegramClient
    from telethon.tl.functions.channels import SearchPostsRequest
    from telethon.tl.types import InputPeerEmpty
except ImportError:
    TelegramClient = None
    SearchPostsRequest = None
    InputPeerEmpty = None


def _list_config(key: str) -> list[str]:
    values = config.app.get(key, [])
    if isinstance(values, str):
        values = [value.strip() for value in values.split(",")]
    return [str(value).strip().lstrip("@") for value in values if str(value).strip()]


def _session_file() -> str:
    configured = str(config.app.get("telegram_session_file", "")).strip()
    if configured:
        return configured
    session_dir = utils.storage_dir("telegram", create=True)
    return os.path.join(session_dir, "telethon_news")


def _message_url(chat, message_id: int) -> str:
    username = getattr(chat, "username", "") or ""
    if username:
        return f"https://t.me/{username}/{message_id}"
    return ""


def _story_from_message(message, chat=None) -> NewsStory | None:
    text = (getattr(message, "message", "") or "").strip()
    if not text:
        return None

    title = text.splitlines()[0][:120].strip()
    published_at = ""
    if getattr(message, "date", None):
        published_at = message.date.astimezone(timezone.utc).isoformat()

    source_url = _message_url(chat, message.id)
    media = []
    if getattr(message, "media", None) and source_url:
        media.append(
            NewsMediaAsset(
                provider="telethon",
                url=source_url,
                media_type="article",
                title=title,
                credit=getattr(chat, "title", "") or getattr(chat, "username", ""),
                source_url=source_url,
            )
        )

    return NewsStory(
        provider="telethon",
        title=title,
        summary=text,
        url=source_url,
        published_at=published_at,
        language="",
        country="",
        category="telegram",
        keywords=[],
        media=media,
    )


def _run(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("Telethon provider cannot run inside an active event loop")


class TelethonProvider:
    source_name = "telethon"

    def search(self, query: NewsQueryRequest) -> list[NewsStory]:
        if TelegramClient is None:
            logger.warning("telethon is not installed; install telethon to use MTProto news search")
            return []

        api_id = config.app.get("telegram_api_id", "")
        api_hash = str(config.app.get("telegram_api_hash", "")).strip()
        if not api_id or not api_hash:
            logger.warning("telegram_api_id and telegram_api_hash are not configured")
            return []

        try:
            api_id = int(api_id)
        except (TypeError, ValueError):
            logger.warning("telegram_api_id must be an integer")
            return []

        try:
            return _run(self._search_async(query, api_id, api_hash))
        except Exception as exc:
            logger.error(f"Telethon news search failed: {str(exc)}")
            return []

    async def _search_async(
        self, query: NewsQueryRequest, api_id: int, api_hash: str
    ) -> list[NewsStory]:
        session_file = _session_file()
        channels = _list_config("telegram_user_channels")
        global_search = bool(config.app.get("telegram_global_search", False))
        limit = min(max(query.limit, 1), 50)
        stories = []

        async with TelegramClient(session_file, api_id, api_hash) as client:
            if not await client.is_user_authorized():
                logger.warning(
                    "Telethon session is not authorized. Run tools/telegram_login.py first."
                )
                return []

            for channel in channels:
                entity = await client.get_entity(channel)
                async for message in client.iter_messages(
                    entity, search=query.query or None, limit=limit
                ):
                    story = _story_from_message(message, entity)
                    if story:
                        stories.append(story)
                    if len(stories) >= limit:
                        return stories

            if global_search and query.query and SearchPostsRequest and InputPeerEmpty:
                result = await client(
                    SearchPostsRequest(
                        query=query.query,
                        offset_rate=0,
                        offset_peer=InputPeerEmpty(),
                        offset_id=0,
                        limit=limit,
                    )
                )
                chats_by_id = {getattr(chat, "id", None): chat for chat in result.chats}
                for message in result.messages:
                    peer_id = getattr(message, "peer_id", None)
                    channel_id = getattr(peer_id, "channel_id", None)
                    chat = chats_by_id.get(channel_id)
                    story = _story_from_message(message, chat)
                    if story:
                        stories.append(story)
                    if len(stories) >= limit:
                        break

        return stories
