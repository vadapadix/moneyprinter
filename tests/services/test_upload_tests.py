import tempfile
import unittest
from unittest import mock

from app.services import upload_tests
from app.services.publishers.base import PublishResult


class UploadTestsServiceTest(unittest.TestCase):
    def test_run_upload_test_calls_both_configured_publishers(self):
        publishers = {
            "tiktok": mock.Mock(
                publish=mock.Mock(
                    return_value=PublishResult(
                        platform="tiktok",
                        success=True,
                        status="manual_review_required",
                    )
                )
            ),
            "youtube": mock.Mock(
                publish=mock.Mock(
                    return_value=PublishResult(
                        platform="youtube",
                        success=True,
                        status="uploaded",
                        url="https://www.youtube.com/shorts/test",
                    )
                )
            ),
        }

        with tempfile.NamedTemporaryFile(suffix=".mp4") as video_file, mock.patch.object(
            upload_tests.social_publisher,
            "get_publisher",
            side_effect=lambda platform: publishers[platform],
        ):
            result = upload_tests.run_upload_test(
                video_path=video_file.name,
                platform="both",
                request_id="request-1",
            )

        self.assertEqual(result["platforms_tested"], ["tiktok", "youtube"])
        self.assertEqual(result["results"]["tiktok"]["status"], "manual_review_required")
        self.assertEqual(result["results"]["youtube"]["status"], "uploaded")
        publishers["tiktok"].publish.assert_called_once()
        publishers["youtube"].publish.assert_called_once()

    def test_run_upload_test_rejects_unknown_platform_before_publish(self):
        with mock.patch.object(upload_tests.social_publisher, "get_publisher") as get_publisher:
            with self.assertRaises(ValueError):
                upload_tests.run_upload_test("video.mp4", platform="instagram")

        get_publisher.assert_not_called()


if __name__ == "__main__":
    unittest.main()
