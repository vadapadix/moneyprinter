import tempfile
import unittest
from unittest import mock

from app.services import news_diagnostics


class NewsDiagnosticsTest(unittest.TestCase):
    def test_record_event_persists_jsonable_events(self):
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(
            news_diagnostics.utils,
            "storage_dir",
            lambda sub_dir="", create=False: temp_dir,
        ):
            news_diagnostics.record_event(
                "task-1",
                "news_story_reserved",
                title="Story",
                paths={"video": "a.mp4"},
            )

            events = news_diagnostics.get_task_diagnostics("task-1")

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "news_story_reserved")
        self.assertEqual(events[0]["properties"]["title"], "Story")

    def test_media_summary_tracks_news_sources_and_fallback(self):
        events = [
            {
                "event": "news_related_telegram_search_completed",
                "properties": {
                    "downloaded_count": 1,
                    "total_video_count": 1,
                    "downloaded_paths": ["telegram.mp4"],
                },
            },
            {
                "event": "news_ytdlp_search_completed",
                "properties": {
                    "downloaded_count": 1,
                    "total_video_count": 2,
                    "downloaded_paths": ["yt.mp4"],
                    "attempts": [
                        {"url": "https://example.com/video"},
                        {"skipped_relevance": {"title": "unrelated"}},
                    ],
                },
            },
            {
                "event": "news_stock_fallback_completed",
                "properties": {
                    "source": "pexels",
                    "downloaded_count": 1,
                    "total_video_count": 3,
                },
            },
        ]

        summary = news_diagnostics.media_summary_from_events(events)

        self.assertEqual(summary["status"], "news_media_ready")
        self.assertEqual(summary["total_video_count"], 3)
        self.assertEqual(summary["non_stock_video_count"], 2)
        self.assertTrue(summary["stock_fallback_used"])
        self.assertEqual(summary["used_sources"], ["telethon", "yt-dlp", "pexels"])
        self.assertEqual(summary["stages"][1]["attempt_count"], 2)
        self.assertEqual(summary["stages"][1]["skipped_relevance_count"], 1)


if __name__ == "__main__":
    unittest.main()
