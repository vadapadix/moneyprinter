import unittest

from app.models.schema import NewsMediaAsset, NewsStory
from app.services.news_sources.base import is_direct_video_url, media_asset_to_material


class NewsSourceBaseTest(unittest.TestCase):
    def test_media_asset_to_material_accepts_video(self):
        asset = NewsMediaAsset(
            provider="demo",
            url="https://example.com/video.mp4",
            media_type="video",
            title="Demo clip",
            credit="Example",
            duration=12,
        )

        material = media_asset_to_material(asset)

        self.assertEqual(material.provider, "demo")
        self.assertEqual(material.url, "https://example.com/video.mp4")
        self.assertEqual(material.duration, 12)

    def test_news_story_defaults_are_safe(self):
        story = NewsStory(title="Headline")

        self.assertEqual(story.title, "Headline")
        self.assertEqual(story.media, [])
        self.assertEqual(story.keywords, [])

    def test_direct_video_url_ignores_query_string(self):
        self.assertTrue(is_direct_video_url("https://example.com/clip.mp4?token=123"))
        self.assertFalse(is_direct_video_url("https://example.com/article"))


if __name__ == "__main__":
    unittest.main()
