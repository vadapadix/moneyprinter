import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock

from app.models.schema import NewsQueryRequest
from app.services.news_sources import get_provider
from app.services.news_sources.telethon_source import (
    TelethonProvider,
    _list_config,
    _story_from_message,
)


class TelethonProviderTest(unittest.TestCase):
    def test_registry_returns_telethon_provider(self):
        self.assertIsInstance(get_provider("telethon"), TelethonProvider)

    def test_list_config_accepts_comma_string(self):
        with mock.patch.dict(
            "app.services.news_sources.telethon_source.config.app",
            {"telegram_user_channels": "@one, two"},
            clear=False,
        ):
            self.assertEqual(_list_config("telegram_user_channels"), ["one", "two"])

    def test_story_from_message_uses_channel_url(self):
        message = SimpleNamespace(
            id=7,
            message="Breaking update\nMore context",
            date=datetime(2026, 5, 31, tzinfo=timezone.utc),
            media=None,
        )
        chat = SimpleNamespace(username="demo_news", title="Demo News")

        story = _story_from_message(message, chat)

        self.assertEqual(story.provider, "telethon")
        self.assertEqual(story.title, "Breaking update")
        self.assertEqual(story.url, "https://t.me/demo_news/7")

    def test_missing_telethon_dependency_returns_empty(self):
        with mock.patch(
            "app.services.news_sources.telethon_source.TelegramClient", None
        ):
            result = TelethonProvider().search(NewsQueryRequest(query="news"))

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
