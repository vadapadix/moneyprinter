import tempfile
import unittest
from unittest import mock

from app.models.schema import NewsStory, VideoParams
from app.services import news_diagnostics, news_history, news_pipeline, task


class TaskNewsHistoryTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage_patches = [
            mock.patch.object(
                news_history.utils,
                "storage_dir",
                lambda sub_dir="", create=False: self.temp_dir.name,
            ),
            mock.patch.object(
                news_diagnostics.utils,
                "storage_dir",
                lambda sub_dir="", create=False: self.temp_dir.name,
            ),
        ]
        for patcher in self.storage_patches:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.storage_patches):
            patcher.stop()
        self.temp_dir.cleanup()

    def _params_for_story(self, story: NewsStory) -> VideoParams:
        return VideoParams(
            video_subject=news_pipeline.build_script_subject(story),
            video_source="news",
            news_source_context=news_pipeline.build_source_context(story),
        )

    def test_mark_news_story_result_completes_reserved_story(self):
        story = NewsStory(
            provider="guardian",
            title="Parliament approves emergency budget",
            summary="Lawmakers approved an emergency budget after a late vote.",
            url="https://example.com/news/1",
        )
        news_history.reserve_story(story, run_id="run-1", task_id="task-1")

        task._mark_news_story_result(
            "task-1",
            self._params_for_story(story),
            success=True,
            videos=["final.mp4"],
            publish_results=[{"platform": "youtube", "success": True}],
            reason="completed",
        )

        entry = news_history.load_history()["stories"][news_history.story_key(story)]
        diagnostics = news_diagnostics.get_task_diagnostics("task-1")

        self.assertEqual(entry["status"], "completed")
        self.assertEqual(entry["video_count"], 1)
        self.assertEqual(entry["publish_count"], 1)
        self.assertEqual(diagnostics[-1]["event"], "news_history_finalized")
        self.assertTrue(diagnostics[-1]["properties"]["success"])

    def test_fail_news_task_marks_reserved_story_failed(self):
        story = NewsStory(
            provider="telethon",
            title="Storm disrupts airport operations",
            summary="Flights were delayed after severe weather moved through the city.",
            url="https://t.me/demo/42",
        )
        news_history.reserve_story(story, run_id="run-2", task_id="task-2")

        task._fail_news_task(
            "task-2",
            self._params_for_story(story),
            reason="audio_generation_failed",
        )

        entry = news_history.load_history()["stories"][news_history.story_key(story)]
        diagnostics = news_diagnostics.get_task_diagnostics("task-2")

        self.assertEqual(entry["status"], "failed")
        self.assertEqual(diagnostics[-2]["event"], "news_history_finalized")
        self.assertEqual(diagnostics[-2]["properties"]["reason"], "audio_generation_failed")
        self.assertEqual(diagnostics[-1]["event"], "news_task_failed")


if __name__ == "__main__":
    unittest.main()
