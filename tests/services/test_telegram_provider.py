import unittest
from unittest import mock

from app.models.schema import NewsQueryRequest
from app.services.news_sources.telegram import TelegramProvider


class FakeTelegramResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "ok": True,
            "result": [
                {
                    "channel_post": {
                        "chat": {"id": -100123, "title": "Demo News", "username": "demo_news"},
                        "date": 1780000000,
                        "text": "Breaking: demo event happened\nMore context",
                    }
                },
                {
                    "channel_post": {
                        "chat": {"id": -100999, "title": "Other News"},
                        "date": 1780000001,
                        "text": "Breaking: should be ignored",
                    }
                },
            ],
        }


class TelegramProviderTest(unittest.TestCase):
    def test_telegram_provider_reads_configured_updates(self):
        with mock.patch.dict(
            "app.services.news_sources.telegram.config.app",
            {
                "telegram_bot_token": "token",
                "telegram_channel_ids": ["@demo_news"],
                "telegram_max_messages": 20,
            },
            clear=False,
        ), mock.patch(
            "app.services.news_sources.telegram.requests.get",
            return_value=FakeTelegramResponse(),
        ) as get_mock:
            stories = TelegramProvider().search(
                NewsQueryRequest(query="demo", limit=5, language="en", country="us")
            )

        self.assertEqual(len(stories), 1)
        self.assertEqual(stories[0].provider, "telegram")
        self.assertTrue(stories[0].title.startswith("Breaking"))
        self.assertIn("More context", stories[0].summary)
        self.assertEqual(get_mock.call_args.kwargs["params"]["allowed_updates"], '["channel_post"]')


if __name__ == "__main__":
    unittest.main()
