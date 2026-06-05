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

    def test_unknown_title_falls_back_to_source_title(self):
        def fake_generate_response(prompt):
            return """
            {
                "title": "unknown",
                "description": "A concise update.",
                "hashtags": ["#News"],
                "youtube_tags": ["News"],
                "category_id": "25",
                "contains_synthetic_media": true,
                "platform_captions": {
                    "tiktok": "A concise update #News"
                }
            }
            """

        with mock.patch.object(
            social_metadata.llm, "_generate_response", fake_generate_response
        ):
            result = social_metadata.generate_social_metadata(
                video_subject="Long prompt text",
                video_script="Story script",
                video_terms=["news"],
                default_title="Real source headline",
            )

        self.assertEqual(result.title, "Real source headline")
        self.assertIn("#Shorts", result.description)
        self.assertEqual(result.platform_captions["tiktok"], "A concise update #News")

    def test_numeric_category_id_from_llm_is_coerced_to_string(self):
        def fake_generate_response(prompt):
            return """
            {
                "title": "Budget vote explained",
                "description": "A concise sourced update. #Shorts",
                "hashtags": ["#News", "#Shorts"],
                "youtube_tags": ["News", "Budget"],
                "category_id": 28,
                "contains_synthetic_media": true,
                "platform_captions": {
                    "tiktok": "Budget vote explained #News #Shorts"
                }
            }
            """

        with mock.patch.object(
            social_metadata.llm, "_generate_response", fake_generate_response
        ):
            result = social_metadata.generate_social_metadata(
                video_subject="Budget vote",
                video_script="Lawmakers approved an emergency budget.",
            )

        self.assertEqual(result.category_id, "28")
        self.assertEqual(result.title, "Budget vote explained")

    def test_error_response_fallback_uses_source_context(self):
        with mock.patch.object(
            social_metadata.llm,
            "_generate_response",
            return_value="Error: quota exceeded",
        ):
            result = social_metadata.generate_social_metadata(
                video_subject="Long generation prompt",
                video_script="Story script",
                video_terms=["ice hockey"],
                source_context={
                    "title": "USA and Canada to meet in Olympic hockey final",
                    "summary": "The two teams will play for gold after winning their semifinals.",
                    "source_url": "https://example.com/hockey-final",
                    "keywords": ["Olympics", "Hockey"],
                },
            )

        self.assertEqual(result.title, "USA and Canada to meet in Olympic hockey final")
        self.assertIn("The two teams will play for gold", result.description)
        self.assertIn("Source: https://example.com/hockey-final", result.description)
        self.assertIn("#Shorts", result.description)
        self.assertIn("Olympics", result.youtube_tags)
        self.assertIn("ice hockey", result.youtube_tags)
        self.assertIn("#Hockey", result.hashtags)
        self.assertTrue(result.platform_captions["tiktok"].startswith("USA and Canada"))

    def test_invalid_json_fallback_uses_default_title_before_prompt(self):
        with mock.patch.object(
            social_metadata.llm,
            "_generate_response",
            return_value="not json",
        ):
            result = social_metadata.generate_social_metadata(
                video_subject="Write a short factual news voiceover in English...",
                video_terms=["markets"],
                default_title="Central bank announces rate decision",
                source_context={
                    "title": "Source title",
                    "summary": "Officials announced a new decision.",
                },
            )

        self.assertEqual(result.title, "Central bank announces rate decision")
        self.assertNotEqual(result.title.lower(), "unknown")
        self.assertIn("Officials announced a new decision.", result.description)


if __name__ == "__main__":
    unittest.main()
