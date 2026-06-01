import unittest
from unittest import mock

from app.services import video


class VideoBrandingTest(unittest.TestCase):
    def test_brand_intro_duration_is_capped_by_video_duration(self):
        with mock.patch.dict(
            "app.services.video.config.app",
            {"brand_intro_duration": 2.2},
            clear=False,
        ):
            self.assertEqual(video._brand_intro_duration(1.5), 1.5)
            self.assertEqual(video._brand_intro_duration(10), 2.2)

    def test_brand_intro_duration_can_be_disabled_by_zero(self):
        with mock.patch.dict(
            "app.services.video.config.app",
            {"brand_intro_duration": 0},
            clear=False,
        ):
            self.assertEqual(video._brand_intro_duration(10), 0.0)


if __name__ == "__main__":
    unittest.main()
