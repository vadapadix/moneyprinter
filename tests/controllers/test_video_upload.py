import os
import tempfile
import unittest
from unittest import mock

from app.controllers.v1 import video
from app.services.publishers.base import PublishResult


class FakeUploadFile:
    filename = "short.mp4"

    def __init__(self, content: bytes = b"video"):
        self.file = tempfile.TemporaryFile()
        self.file.write(content)
        self.file.seek(0)

    def close(self):
        self.file.close()


class VideoUploadControllerTest(unittest.TestCase):
    def test_test_upload_uses_configured_social_publisher(self):
        upload = FakeUploadFile()
        publisher = mock.Mock()
        publisher.publish.return_value = PublishResult(
            platform="tiktok",
            success=True,
            status="manual_review_required",
            raw={"mode": "browser_assist"},
        )

        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(
            video.utils,
            "storage_dir",
            lambda sub_dir="", create=False: temp_dir,
        ), mock.patch.object(
            video.base,
            "get_task_id",
            return_value="request-1",
        ), mock.patch.object(
            video.social_publisher,
            "get_publisher",
            return_value=publisher,
        ) as get_publisher_mock:
            response = video.test_upload_video(
                request=mock.Mock(headers={}), file=upload, platform="tiktok"
            )

        upload.close()
        self.assertEqual(response["status"], 200)
        self.assertEqual(response["data"]["results"]["tiktok"]["status"], "manual_review_required")
        self.assertEqual(response["data"]["results"]["tiktok"]["raw"], {"mode": "browser_assist"})
        get_publisher_mock.assert_called_once_with("tiktok")
        self.assertFalse(os.path.exists(os.path.join(temp_dir, "test_upload_request-1_short.mp4")))


if __name__ == "__main__":
    unittest.main()
