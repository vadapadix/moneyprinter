import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.models.schema import SocialMetadata
from app.services import social_metadata


class TestSocialMetadata(unittest.TestCase):
    def test_fallback_adds_shorts_and_normalizes_hashtags(self):
        result = social_metadata.fallback_metadata(
            "Money saving hacks", ["money tips", "#shorts", "AI tools!"]
        )

        self.assertEqual(result.title, "Money saving hacks")
        self.assertIn("#Shorts", result.hashtags)
        self.assertIn("#AItools", result.hashtags)
        self.assertIn("#Shorts", result.description)

    def test_generate_parses_json_response(self):
        response = """
        {
          "title": "Fast savings trick",
          "description": "Try this today",
          "hashtags": ["#Money", "finance tips"],
          "youtube_tags": ["money", "saving"],
          "category_id": "22",
          "contains_synthetic_media": true,
          "platform_captions": {"tiktok": "Fast savings trick #Money"}
        }
        """

        with patch("app.services.social_metadata.llm._generate_response", return_value=response):
            result = social_metadata.generate_social_metadata(
                "Money saving hacks", "script", ["money"]
            )

        self.assertEqual(result.title, "Fast savings trick")
        self.assertIn("#Shorts", result.hashtags)
        self.assertEqual(result.platform_captions["tiktok"], "Fast savings trick #Money")

    def test_normalize_truncates_long_title(self):
        result = social_metadata.normalize_metadata(
            SocialMetadata(title="x" * 140, description="desc")
        )

        self.assertLessEqual(len(result.title), 95)


if __name__ == "__main__":
    unittest.main()
