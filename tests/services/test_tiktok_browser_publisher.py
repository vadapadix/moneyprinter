import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.models.schema import PublishPrivacy, SocialMetadata
from app.services.publishers import tiktok_browser
from app.services.publishers.tiktok_browser import TikTokBrowserPublisher


class TikTokBrowserPublisherTest(unittest.TestCase):
    def test_build_tiktok_caption_prefers_platform_caption_and_adds_hashtags(self):
        metadata = SocialMetadata(
            title="Fallback title",
            description="Fallback description",
            hashtags=["News", "#AI", "news"],
            platform_captions={"tiktok": "Breaking update"},
        )

        caption = tiktok_browser.build_tiktok_caption(metadata)

        self.assertEqual(caption, "Breaking update\n\n#News #AI")

    def test_publish_prepares_package_and_opens_upload_page(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = os.path.join(temp_dir, "short.mp4")
            Path(video_path).write_bytes(b"video")

            publisher = TikTokBrowserPublisher.__new__(TikTokBrowserPublisher)
            publisher.enabled = True
            publisher.upload_url = "https://www.tiktok.com/tiktokstudio/upload"
            publisher.upload_dir = os.path.join(temp_dir, "uploads")
            publisher.open_upload_page = True
            publisher.copy_caption = True

            with mock.patch.object(
                tiktok_browser, "copy_text_to_clipboard", return_value=True
            ) as copy_mock, mock.patch.object(
                tiktok_browser, "open_upload_page", return_value=True
            ) as open_mock:
                result = publisher.publish(
                    video_path=video_path,
                    metadata=SocialMetadata(
                        title="News title",
                        description="News description",
                        hashtags=["Shorts", "Breaking"],
                    ),
                    privacy=PublishPrivacy.private,
                )

            self.assertTrue(result.success)
            self.assertEqual(result.status, "manual_review_required")
            self.assertTrue(result.raw["requires_user_action"])
            self.assertTrue(result.raw["clipboard_copied"])
            self.assertTrue(result.raw["browser_opened"])
            copy_mock.assert_called_once()
            open_mock.assert_called_once_with(publisher.upload_url)

            package_dir = Path(result.raw["package_dir"])
            self.assertTrue((package_dir / "short.mp4").exists())
            caption = (package_dir / "caption.txt").read_text(encoding="utf-8")
            self.assertIn("#Shorts #Breaking", caption)
            metadata = json.loads((package_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["mode"], "browser_assist")
            self.assertEqual(metadata["privacy"], "private")
            self.assertTrue((package_dir / "open_upload.html").exists())

    def test_publish_returns_not_configured_when_disabled(self):
        publisher = TikTokBrowserPublisher.__new__(TikTokBrowserPublisher)
        publisher.enabled = False

        result = publisher.publish("missing.mp4", SocialMetadata())

        self.assertFalse(result.success)
        self.assertEqual(result.status, "not_configured")


if __name__ == "__main__":
    unittest.main()
