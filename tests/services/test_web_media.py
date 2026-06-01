import unittest
from unittest import mock

from app.models.schema import NewsStory
from app.services import web_media


class WebMediaTest(unittest.TestCase):
    def test_extract_urls_from_story_text(self):
        self.assertEqual(
            web_media.extract_urls("Read https://example.com/a. Then https://b.test/x"),
            ["https://example.com/a", "https://b.test/x"],
        )

    def test_discover_story_media_finds_og_video(self):
        story = NewsStory(
            title="Story title",
            summary="Read more https://example.com/story",
            url="",
        )
        response = mock.Mock()
        response.url = "https://example.com/story"
        response.text = '<meta property="og:video" content="https://cdn.example.com/video.mp4">'
        response.raise_for_status.return_value = None

        with mock.patch.object(web_media.requests, "get", return_value=response):
            assets = web_media.discover_story_media(story, limit=1)

        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0].media_type, "video")
        self.assertEqual(assets[0].url, "https://cdn.example.com/video.mp4")

    def test_discover_story_media_searches_title_variants(self):
        story = NewsStory(
            provider="guardian",
            title="Major headline",
            category="world",
        )
        calls = []

        def fake_search(query, limit=4):
            calls.append(query)
            return []

        with mock.patch.object(web_media, "_search_urls", fake_search):
            assets = web_media.discover_story_media(story)

        self.assertEqual(assets, [])
        self.assertIn("Major headline", calls)
        self.assertIn("Major headline guardian", calls)
        self.assertIn("Major headline world", calls)


if __name__ == "__main__":
    unittest.main()
