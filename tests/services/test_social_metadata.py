import unittest
from unittest import mock

from app.models.schema import SocialMetadata
from app.services import social_metadata


class SocialMetadataTest(unittest.TestCase):
    def test_normalize_metadata_adds_shorts_and_deduplicates_hashtags(self):
        metadata = SocialMetadata(
            title="Breaking update",
            description="A concise summary",
            hashtags=["news", "#Ukraine", "news"],
            youtube_tags=["news", "Ukraine", "#Shorts"],
            platform_captions={"TikTok": "TikTok caption"},
        )

        result = social_metadata.normalize_metadata(metadata, default_title="Fallback")

        self.assertEqual(result.title, "Breaking update")
        self.assertIn("#Shorts", result.hashtags)
        self.assertIn("#news", result.hashtags)
        self.assertIn("#Ukraine", result.hashtags)
        self.assertEqual(result.hashtags.count("#news"), 1)
        self.assertEqual(result.platform_captions["tiktok"], "TikTok caption")
        self.assertIn("#Shorts", result.description)

    def test_generate_social_metadata_prompt_includes_source_context(self):
        captured = {}

        def fake_generate_response(prompt):
            captured["prompt"] = prompt
            return """
            {
                "title": "Source-backed short",
                "description": "A sourced summary. Source: https://example.com/story",
                "hashtags": ["#News", "#Shorts"],
                "youtube_tags": ["News", "Shorts"],
                "category_id": "25",
                "contains_synthetic_media": true,
                "platform_captions": {
                    "tiktok": "A sourced summary #News #Shorts",
                    "youtube": "A sourced summary"
                }
            }
            """

        with mock.patch.object(
            social_metadata.llm, "_generate_response", fake_generate_response
        ):
            result = social_metadata.generate_social_metadata(
                video_subject="Source-backed short",
                video_script="Story script",
                video_terms=["news"],
                platforms=["youtube", "tiktok"],
                source_context={
                    "provider": "newsdata",
                    "source_url": "https://example.com/story",
                },
            )

        self.assertIn("source_context", captured["prompt"])
        self.assertIn("https://example.com/story", captured["prompt"])
        self.assertTrue(result.description.startswith("A sourced summary."))
        self.assertTrue(result.platform_captions["tiktok"].startswith("A sourced summary"))


if __name__ == "__main__":
    unittest.main()
