import os
import tempfile
import unittest
from unittest import mock

from app.models.schema import PublishPrivacy, SocialMetadata
from app.services.publishers.youtube import YouTubeShortsPublisher


class YouTubePublisherTest(unittest.TestCase):
    def test_build_upload_body_reports_metadata_quality_and_removes_unknown_title(self):
        publisher = YouTubeShortsPublisher.__new__(YouTubeShortsPublisher)
        publisher.default_privacy = "private"

        body, normalized, quality = publisher.build_upload_body(
            video_path=os.path.join("tasks", "generated-news-short.mp4"),
            metadata=SocialMetadata(
                title="unknown",
                description="",
                youtube_tags=[],
                hashtags=[],
            ),
            privacy=PublishPrivacy.draft,
        )

        self.assertEqual(body["snippet"]["title"], "generated-news-short")
        self.assertEqual(normalized.title, "generated-news-short")
        self.assertEqual(body["status"]["privacyStatus"], "private")
        self.assertEqual(quality["title_source"], "normalized_fallback")
        self.assertTrue(quality["has_shorts_marker"])
        self.assertGreater(quality["description_length"], 0)

    def test_publish_normalizes_empty_metadata_before_upload(self):
        captured = {}
        response = mock.Mock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.return_value = {"id": "video123"}

        publisher = YouTubeShortsPublisher.__new__(YouTubeShortsPublisher)
        publisher.enabled = True
        publisher.access_token = "access-token"
        publisher.default_privacy = "private"

        def fake_upload(video_path, body):
            captured["body"] = body
            return response

        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = os.path.join(temp_dir, "news_upload_test.mp4")
            with open(video_path, "wb") as handle:
                handle.write(b"video")

            with mock.patch.object(publisher, "_upload_once", side_effect=fake_upload):
                result = publisher.publish(
                    video_path=video_path,
                    metadata=SocialMetadata(title="", description="", youtube_tags=[]),
                    privacy=PublishPrivacy.private,
                )

        self.assertTrue(result.success)
        self.assertEqual(captured["body"]["snippet"]["title"], "news_upload_test")
        self.assertIn("#Shorts", captured["body"]["snippet"]["description"])
        self.assertEqual(captured["body"]["status"]["privacyStatus"], "private")
        self.assertEqual(result.raw["metadata_quality"]["title"], "news_upload_test")
        self.assertEqual(
            result.raw["upload_body"]["snippet"]["title"], "news_upload_test"
        )


if __name__ == "__main__":
    unittest.main()
