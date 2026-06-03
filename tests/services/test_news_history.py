import tempfile
import unittest
from unittest import mock

from app.models.schema import NewsStory
from app.services import news_history


class NewsHistoryTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage_patch = mock.patch.object(
            news_history.utils,
            "storage_dir",
            lambda sub_dir="", create=False: self.temp_dir.name,
        )
        self.storage_patch.start()

    def tearDown(self):
        self.storage_patch.stop()
        self.temp_dir.cleanup()

    def test_story_key_prefers_url(self):
        story = NewsStory(
            provider="guardian",
            title="Market update",
            url="https://example.com/story",
        )

        self.assertEqual(news_history.story_key(story), "url:https://example.com/story")

    def test_filter_new_stories_skips_reserved_and_batch_duplicates(self):
        first = NewsStory(provider="newsdata", title="First", url="https://a.test/1")
        duplicate = NewsStory(provider="newsdata", title="First copy", url="https://a.test/1")
        second = NewsStory(provider="newsdata", title="Second", url="https://a.test/2")
        news_history.reserve_story(first, run_id="run-1", task_id="task-1")

        result = news_history.filter_new_stories([first, duplicate, second], limit=2)

        self.assertEqual([story.url for story in result], ["https://a.test/2"])

    def test_filter_new_stories_skips_same_strong_headline_from_different_url(self):
        first = NewsStory(
            provider="newsdata",
            title="Central bank announces emergency rate decision",
            url="https://news.example/rate-decision",
        )
        duplicate_headline = NewsStory(
            provider="guardian",
            title="Central bank announces emergency rate decision",
            url="https://guardian.example/rate-decision",
        )
        fresh = NewsStory(
            provider="guardian",
            title="Court approves new election timetable",
            url="https://guardian.example/election-timetable",
        )
        news_history.reserve_story(first, run_id="run-1", task_id="task-1")

        result = news_history.filter_new_stories(
            [duplicate_headline, fresh], limit=2
        )

        self.assertEqual([story.title for story in result], [fresh.title])

    def test_mark_story_result_updates_reserved_story(self):
        story = NewsStory(provider="telethon", title="Update", url="https://t.me/demo/1")
        news_history.reserve_story(story, run_id="run-1", task_id="task-1")

        news_history.mark_story_result(
            story,
            task_id="task-1",
            success=True,
            videos=["video.mp4"],
            publish_results=[{"platform": "youtube", "success": True}],
        )

        entry = news_history.load_history()["stories"][news_history.story_key(story)]
        self.assertEqual(entry["status"], "completed")
        self.assertEqual(entry["video_count"], 1)
        self.assertEqual(entry["publish_count"], 1)


if __name__ == "__main__":
    unittest.main()
