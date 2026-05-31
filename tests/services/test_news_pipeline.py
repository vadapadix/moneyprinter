import unittest
from unittest import mock

from app.models.schema import NewsMediaAsset, NewsStory, VideoParams
from app.services import news_pipeline


class NewsPipelineTest(unittest.TestCase):
    def test_build_materials_uses_direct_video_assets(self):
        story = NewsStory(
            title="Event",
            media=[
                NewsMediaAsset(
                    provider="demo",
                    url="https://example.com/clip.mp4",
                    media_type="video",
                    duration=9,
                ),
                NewsMediaAsset(
                    provider="demo",
                    url="https://example.com/image.jpg",
                    media_type="image",
                ),
            ],
        )

        materials = news_pipeline.build_materials_from_story(story)

        self.assertEqual(len(materials), 1)
        self.assertEqual(materials[0].url, "https://example.com/clip.mp4")
        self.assertEqual(materials[0].duration, 9)

    def test_prepare_news_context_updates_video_params(self):
        params = VideoParams(
            video_source="news",
            video_subject="markets",
            news_source="newsdata",
        )
        story = NewsStory(
            provider="newsdata",
            title="Market update",
            summary="Stocks moved today",
            url="https://news.example/story",
            keywords=["markets"],
            media=[
                NewsMediaAsset(
                    provider="newsdata",
                    url="https://news.example/clip.mp4",
                    media_type="video",
                    duration=12,
                )
            ],
        )

        with mock.patch.object(news_pipeline.news_sources, "search", return_value=[story]):
            result = news_pipeline.prepare_news_context(params)

        self.assertIs(result, story)
        self.assertEqual(params.video_subject, "Market update")
        self.assertIn("Stocks moved today", params.video_script)
        self.assertEqual(params.news_source_context["source_url"], "https://news.example/story")
        self.assertEqual(params.news_media_assets[0]["url"], "https://news.example/clip.mp4")

    def test_prepare_news_context_reuses_existing_context(self):
        params = VideoParams(
            video_subject="",
            video_source="news",
            news_source_context={
                "provider": "telethon",
                "title": "Existing story",
                "summary": "Already selected",
                "source_url": "https://t.me/demo/1",
                "media": [],
            },
        )

        with mock.patch.object(news_pipeline.news_sources, "search") as search_mock:
            story = news_pipeline.prepare_news_context(params)

        search_mock.assert_not_called()
        self.assertEqual(story.title, "Existing story")
        self.assertEqual(params.video_subject, "Existing story")
        self.assertIn("Already selected", params.video_script)


if __name__ == "__main__":
    unittest.main()
