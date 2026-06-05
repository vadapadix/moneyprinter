import unittest
from unittest import mock

from app.services.publishers.base import PublishResult
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

    def test_publish_existing_task_normalizes_unknown_metadata_from_news_context(self):
        publisher = mock.Mock()
        publisher.publish.return_value = PublishResult(
            platform="youtube",
            success=True,
            status="uploaded",
            post_id="video-1",
        )
        updates = {}

        with mock.patch.object(
            social_publisher.sm.state,
            "get_task",
            return_value={
                "videos": ["D:/tmp/generated-news.mp4"],
                "social_metadata": {
                    "title": "unknown",
                    "description": "",
                    "hashtags": [],
                    "youtube_tags": [],
                    "category_id": "22",
                    "contains_synthetic_media": True,
                    "platform_captions": {},
                },
                "news_source_context": {
                    "title": "Court issues major election ruling",
                },
            },
        ), mock.patch.object(
            social_publisher, "get_publisher", return_value=publisher
        ), mock.patch.object(
            social_publisher.sm.state,
            "update_task",
            side_effect=lambda task_id, **kwargs: updates.update(kwargs),
        ):
            results = social_publisher.publish_existing_task(
                "task-1",
                platforms=["youtube"],
            )

        self.assertTrue(results[0]["success"])
        published_metadata = publisher.publish.call_args.args[1]
        self.assertEqual(published_metadata.title, "Court issues major election ruling")
        self.assertNotEqual(updates["social_metadata"]["title"].lower(), "unknown")
        self.assertEqual(
            updates["social_metadata"]["title"],
            "Court issues major election ruling",
        )

    def test_publish_existing_task_falls_back_to_video_filename_for_empty_metadata(self):
        publisher = mock.Mock()
        publisher.publish.return_value = PublishResult(
            platform="youtube",
            success=True,
            status="uploaded",
            post_id="video-1",
        )
        updates = {}

        with mock.patch.object(
            social_publisher.sm.state,
            "get_task",
            return_value={
                "videos": ["D:/tmp/story-final.mp4"],
                "social_metadata": {"title": "unknown"},
            },
        ), mock.patch.object(
            social_publisher, "get_publisher", return_value=publisher
        ), mock.patch.object(
            social_publisher.sm.state,
            "update_task",
            side_effect=lambda task_id, **kwargs: updates.update(kwargs),
        ):
            social_publisher.publish_existing_task("task-1", platforms=["youtube"])

        published_metadata = publisher.publish.call_args.args[1]
        self.assertEqual(published_metadata.title, "story-final")
        self.assertEqual(updates["social_metadata"]["title"], "story-final")


if __name__ == "__main__":
    unittest.main()
