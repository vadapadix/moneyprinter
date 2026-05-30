import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.config import config
from app.models.schema import PublishPrivacy, SocialMetadata
from app.services.publishers.tiktok import TikTokPublisher
from app.services.publishers.youtube import YouTubeShortsPublisher
from app.services.social_publisher import publish_video


class TestPublishers(unittest.TestCase):
    def setUp(self):
        self.original_app_config = dict(config.app)

    def tearDown(self):
        config.app.clear()
        config.app.update(self.original_app_config)

    def test_youtube_disabled_without_credentials(self):
        config.app["youtube_upload_enabled"] = True
        config.app["youtube_access_token"] = ""
        config.app["youtube_refresh_token"] = ""
        config.app["youtube_client_id"] = ""
        config.app["youtube_client_secret"] = ""

        result = YouTubeShortsPublisher().publish(
            "missing.mp4", SocialMetadata(title="Title")
        )

        self.assertFalse(result.success)
        self.assertEqual(result.status, "disabled")

    def test_youtube_publish_posts_metadata(self):
        config.app["youtube_upload_enabled"] = True
        config.app["youtube_access_token"] = "token"
        config.app["youtube_refresh_token"] = ""
        config.app["youtube_client_id"] = ""
        config.app["youtube_client_secret"] = ""
        fake_response = SimpleNamespace(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: {"id": "yt123"},
        )

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as handle:
            handle.write(b"fake-video")
            video_path = handle.name

        try:
            with patch(
                "app.services.publishers.youtube.requests.post",
                return_value=fake_response,
            ) as post:
                result = YouTubeShortsPublisher().publish(
                    video_path,
                    SocialMetadata(
                        title="Title",
                        description="Description #Shorts",
                        youtube_tags=["shorts"],
                    ),
                    PublishPrivacy.private,
                )
        finally:
            os.remove(video_path)

        self.assertTrue(result.success)
        self.assertEqual(result.url, "https://www.youtube.com/shorts/yt123")
        self.assertEqual(post.call_args.kwargs["params"]["part"], "snippet,status")

    def test_publish_video_reports_unsupported_platform(self):
        result = publish_video(
            "video.mp4", SocialMetadata(title="Title"), platforms=["unknown"]
        )

        self.assertEqual(result[0]["status"], "unsupported")

    def test_tiktok_disabled_without_credentials(self):
        config.app["tiktok_upload_enabled"] = True
        config.app["tiktok_access_token"] = ""
        config.app["tiktok_refresh_token"] = ""
        config.app["tiktok_token_expires_at"] = 0

        result = TikTokPublisher().publish("missing.mp4", SocialMetadata(title="Title"))

        self.assertFalse(result.success)
        self.assertEqual(result.status, "disabled")

    def test_tiktok_source_info_uses_file_size_for_small_files(self):
        publisher = TikTokPublisher()

        source_info = publisher._source_info(10)

        self.assertEqual(source_info["video_size"], 10)
        self.assertEqual(source_info["chunk_size"], 10)
        self.assertEqual(source_info["total_chunk_count"], 1)

    def test_tiktok_source_info_uses_single_chunk_up_to_64mb(self):
        publisher = TikTokPublisher()

        source_info = publisher._source_info(17_700_000)

        self.assertEqual(source_info["video_size"], 17_700_000)
        self.assertEqual(source_info["chunk_size"], 17_700_000)
        self.assertEqual(source_info["total_chunk_count"], 1)

    def test_tiktok_source_info_uses_floor_chunk_count(self):
        publisher = TikTokPublisher()
        publisher.chunk_size = 10_000_000

        source_info = publisher._source_info(70_000_123)

        self.assertEqual(source_info["chunk_size"], 10_000_000)
        self.assertEqual(source_info["total_chunk_count"], 7)

    def test_tiktok_read_chunks_puts_remainder_in_last_chunk(self):
        chunks = list(TikTokPublisher._read_chunks(
            video_file=SimpleNamespace(read=self._make_reader(b"1234567890123")),
            video_size=13,
            chunk_size=5,
            total_chunk_count=2,
        ))

        self.assertEqual(chunks[0], (0, 4, b"12345"))
        self.assertEqual(chunks[1], (5, 12, b"67890123"))

    def test_tiktok_publish_initializes_and_uploads_file(self):
        config.app["tiktok_upload_enabled"] = True
        config.app["tiktok_access_token"] = "token"
        config.app["tiktok_refresh_token"] = ""
        config.app["tiktok_token_expires_at"] = 0
        fake_init_response = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "data": {
                    "publish_id": "pub123",
                    "upload_url": "https://upload.example/tiktok",
                },
                "error": {"code": "ok"},
            },
        )
        fake_upload_response = SimpleNamespace(raise_for_status=lambda: None)

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as handle:
            handle.write(b"fake-video")
            video_path = handle.name

        try:
            with patch(
                "app.services.publishers.tiktok.requests.post",
                return_value=fake_init_response,
            ) as post, patch(
                "app.services.publishers.tiktok.requests.put",
                return_value=fake_upload_response,
            ) as put:
                result = TikTokPublisher().publish(
                    video_path,
                    SocialMetadata(
                        description="Caption",
                        hashtags=["#Shorts"],
                        contains_synthetic_media=True,
                    ),
                    PublishPrivacy.private,
                )
        finally:
            os.remove(video_path)

        self.assertTrue(result.success)
        self.assertEqual(result.status, "processing")
        self.assertEqual(result.post_id, "pub123")
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"], "Bearer token"
        )
        self.assertEqual(put.call_args.args[0], "https://upload.example/tiktok")
        self.assertEqual(put.call_args.kwargs["headers"]["Content-Range"], "bytes 0-9/10")

    @staticmethod
    def _make_reader(data):
        position = {"value": 0}

        def read(size):
            start = position["value"]
            end = min(start + size, len(data))
            position["value"] = end
            return data[start:end]

        return read


if __name__ == "__main__":
    unittest.main()
