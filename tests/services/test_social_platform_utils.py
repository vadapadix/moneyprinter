import unittest

from app.models.schema import SocialPlatform
from app.services.social_platform_utils import platform_value, platform_values


class SocialPlatformUtilsTest(unittest.TestCase):
    def test_platform_value_accepts_enum_and_string(self):
        self.assertEqual(platform_value(SocialPlatform.youtube), "youtube")
        self.assertEqual(platform_value("tiktok"), "tiktok")

    def test_platform_values_accepts_mixed_values(self):
        self.assertEqual(
            platform_values([SocialPlatform.youtube, "tiktok"]),
            ["youtube", "tiktok"],
        )


if __name__ == "__main__":
    unittest.main()
