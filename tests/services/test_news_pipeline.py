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

    def test_enrich_story_media_appends_web_videos(self):
        story = NewsStory(title="Story", summary="See https://example.com/story")
        asset = NewsMediaAsset(
            provider="web",
            url="https://cdn.example.com/news.mp4",
            media_type="video",
        )

        with mock.patch.object(news_pipeline.web_media, "discover_story_media", return_value=[asset]):
            enriched = news_pipeline.enrich_story_media(story)

        self.assertEqual(enriched.media[0].url, "https://cdn.example.com/news.mp4")

    def test_discover_related_telegram_video_materials_searches_telethon(self):
        video_story = NewsStory(
            provider="telethon",
            title="Related clip",
            media=[
                NewsMediaAsset(
                    provider="telethon",
                    url="C:/clips/related.mp4",
                    media_type="video",
                    duration=8,
                ),
                NewsMediaAsset(
                    provider="telethon",
                    url="https://example.com/image.jpg",
                    media_type="image",
                ),
            ],
        )

        with mock.patch.dict(
            "app.services.news_pipeline.config.app",
            {"news_related_telegram_video_enabled": True},
            clear=False,
        ), mock.patch.object(
            news_pipeline.news_sources,
            "search",
            return_value=[video_story],
        ) as search_mock:
            materials = news_pipeline.discover_related_telegram_video_materials(
                "Central bank decision", limit=1
            )

        self.assertEqual(len(materials), 1)
        self.assertEqual(materials[0].provider, "telethon")
        self.assertEqual(materials[0].url, "C:/clips/related.mp4")
        self.assertEqual(search_mock.call_args.args[0], "telethon")
        self.assertEqual(search_mock.call_args.args[1].query, "Central bank decision")

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

        with mock.patch.object(
            news_pipeline.news_sources,
            "search",
            return_value=[story],
        ), mock.patch.object(
            news_pipeline.web_media,
            "discover_story_media",
            return_value=[],
        ):
            result = news_pipeline.prepare_news_context(params)

        self.assertIs(result, story)
        self.assertIn("Write a short factual news voiceover in English", params.video_subject)
        self.assertIn("Market update", params.video_subject)
        self.assertIn("Stocks moved today", params.video_subject)
        self.assertEqual(params.video_script, "")
        self.assertEqual(params.news_source_context["source_url"], "https://news.example/story")
        self.assertEqual(params.news_media_assets[0]["url"], "https://news.example/clip.mp4")

    def test_build_source_context_collects_related_urls(self):
        story = NewsStory(
            provider="telethon",
            title="Story",
            summary="Read https://news.example/story and watch https://youtu.be/abc123",
            url="https://t.me/demo/1",
            media=[
                NewsMediaAsset(
                    provider="web",
                    url="https://cdn.example.com/clip.mp4",
                    media_type="video",
                    source_url="https://news.example/story",
                )
            ],
        )

        context = news_pipeline.build_source_context(story)

        self.assertEqual(
            context["source_urls"],
            [
                "https://t.me/demo/1",
                "https://news.example/story",
                "https://youtu.be/abc123",
                "https://cdn.example.com/clip.mp4",
            ],
        )

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

        with mock.patch.object(
            news_pipeline.news_sources,
            "search",
        ) as search_mock, mock.patch.object(
            news_pipeline.web_media,
            "discover_story_media",
            return_value=[],
        ):
            story = news_pipeline.prepare_news_context(params)

        search_mock.assert_not_called()
        self.assertEqual(story.title, "Existing story")
        self.assertIn("Existing story", params.video_subject)
        self.assertIn("Already selected", params.video_subject)
        self.assertEqual(params.video_script, "")

    def test_news_script_subject_keeps_headline_and_bans_padding(self):
        story = NewsStory(
            title="Drone strike hits Romanian border town",
            summary="Residents told reporters they fear another attack.",
            url="https://news.example/romania",
        )

        subject = news_pipeline.build_script_subject(story)

        self.assertIn("headline is the angle", subject)
        self.assertIn("Use only facts found in the source material", subject)
        self.assertIn("160-220 spoken words", subject)
        self.assertIn("keep the script shorter instead of padding it", subject)
        self.assertIn("Drone strike hits Romanian border town", subject)


if __name__ == "__main__":
    unittest.main()
