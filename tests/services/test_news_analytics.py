import unittest

from app.models import const
from app.services import news_analytics


class NewsAnalyticsTest(unittest.TestCase):
    def test_summarize_news_items_counts_media_and_publish_quality(self):
        summary = news_analytics.summarize_news_items(
            [
                {
                    "state": const.TASK_STATE_COMPLETE,
                    "videos": ["final-1.mp4"],
                    "social_metadata": {"title": "Real headline"},
                    "news_media_summary": {
                        "status": "news_media_ready",
                        "non_stock_video_count": 2,
                        "stock_fallback_used": True,
                    },
                    "publish_results": [
                        {"platform": "youtube", "success": True},
                        {"platform": "tiktok", "success": False},
                    ],
                },
                {
                    "state": const.TASK_STATE_FAILED,
                    "videos": [],
                    "social_metadata": {"title": "unknown"},
                    "publish_preflight": {
                        "skip_reason": "no_enabled_platforms",
                        "skipped_platforms": [
                            {"platform": "youtube", "reason": "youtube_not_connected"}
                        ],
                    },
                    "news_media_summary": {
                        "status": "stock_fallback_only",
                        "non_stock_video_count": 0,
                        "stock_fallback_used": True,
                    },
                },
            ]
        )

        self.assertEqual(summary["task_count"], 2)
        self.assertEqual(summary["completed_count"], 1)
        self.assertEqual(summary["failed_count"], 1)
        self.assertEqual(summary["generated_video_count"], 1)
        self.assertEqual(summary["publish_attempt_count"], 2)
        self.assertEqual(summary["publish_success_count"], 1)
        self.assertEqual(summary["publish_failed_count"], 1)
        self.assertEqual(summary["publish_blocked_task_count"], 1)
        self.assertEqual(summary["publish_blocked_reasons"], {"no_enabled_platforms": 1})
        self.assertEqual(summary["platforms"]["youtube"]["success"], 1)
        self.assertEqual(summary["platforms"]["tiktok"]["failed"], 1)
        self.assertEqual(summary["non_stock_video_count"], 2)
        self.assertEqual(summary["stock_fallback_task_count"], 2)
        self.assertEqual(summary["stock_only_task_count"], 1)
        self.assertEqual(summary["unknown_title_count"], 1)
        self.assertEqual(summary["generation_success_rate"], 0.5)
        self.assertEqual(summary["publish_success_rate"], 0.5)

    def test_summarize_state_tasks_filters_non_news_tasks(self):
        summary = news_analytics.summarize_state_tasks(
            [
                {"task_id": "normal-task", "state": const.TASK_STATE_COMPLETE},
                {
                    "task_id": "news-task",
                    "news_story": {"title": "Story"},
                    "state": const.TASK_STATE_COMPLETE,
                    "videos": ["final-1.mp4"],
                },
            ]
        )

        self.assertEqual(summary["task_count"], 1)
        self.assertEqual(summary["total_state_task_count"], 2)
        self.assertEqual(summary["generated_video_count"], 1)


if __name__ == "__main__":
    unittest.main()
