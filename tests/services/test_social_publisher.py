import unittest
from unittest import mock

from app.services import social_publisher
from app.services.publishers.tiktok import TikTokPublisher
from app.services.publishers.tiktok_browser import TikTokBrowserPublisher


class SocialPublisherTest(unittest.TestCase):
    def test_get_publisher_uses_tiktok_api_by_default(self):
        with mock.patch.dict(
            "app.services.social_publisher.config.app",
            {"tiktok_publish_mode": "api"},
            clear=False,
        ):
            publisher = social_publisher.get_publisher("tiktok")

        self.assertIsInstance(publisher, TikTokPublisher)

    def test_get_publisher_uses_tiktok_browser_assist_when_configured(self):
        with mock.patch.dict(
            "app.services.social_publisher.config.app",
            {
                "tiktok_publish_mode": "browser_assist",
                "tiktok_browser_upload_enabled": True,
            },
            clear=False,
        ):
            publisher = social_publisher.get_publisher("tiktok")

        self.assertIsInstance(publisher, TikTokBrowserPublisher)


if __name__ == "__main__":
    unittest.main()
