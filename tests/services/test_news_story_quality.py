import unittest

from app.models.schema import NewsMediaAsset, NewsStory
from app.services import news_story_quality


class NewsStoryQualityTest(unittest.TestCase):
    def test_rank_stories_prefers_detailed_story_with_video(self):
        weak = NewsStory(
            provider="newsdata",
            title="Short",
            summary="Tiny",
            url="",
        )
        strong = NewsStory(
            provider="telethon",
            title="Major international update with confirmed details",
            summary="A detailed summary with enough source context to produce a grounded English short. "
            * 3,
            url="https://news.example/story",
            published_at="2026-06-01T10:00:00+00:00",
            keywords=["world", "breaking"],
            media=[
                NewsMediaAsset(
                    provider="telethon",
                    url="https://cdn.example.com/video.mp4",
                    media_type="video",
                )
            ],
        )

        ranked = news_story_quality.rank_stories([weak, strong])

        self.assertEqual(ranked[0].story.title, strong.title)
        self.assertGreater(ranked[0].score, ranked[1].score)
        self.assertIn("direct_video_media", ranked[0].reasons)
        self.assertIn("weak_or_missing_headline", ranked[1].reasons)


if __name__ == "__main__":
    unittest.main()
