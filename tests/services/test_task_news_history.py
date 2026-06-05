import tempfile
import unittest
from unittest import mock

from app.models.schema import MaterialInfo, NewsStory, SocialPlatform, VideoParams
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

    def test_news_materials_use_related_telegram_before_ytdlp(self):
        story = NewsStory(
            provider="guardian",
            title="Central bank announces emergency rate decision",
            summary="Officials announced an emergency rate decision.",
            url="https://example.com/news/rates",
        )
        params = self._params_for_story(story)
        clip_path = f"{self.temp_dir.name}/related.mp4"
        with open(clip_path, "wb") as handle:
            handle.write(b"video")

        with mock.patch.dict(
            "app.services.task.config.app",
            {"news_min_clips": 1},
            clear=False,
        ), mock.patch.object(
            task.news_pipeline,
            "discover_related_telegram_video_materials",
            return_value=[MaterialInfo(provider="telethon", url=clip_path, duration=8)],
        ) as related_mock, mock.patch.object(
            task.news_video_search,
            "search_and_download_report",
        ) as ytdlp_mock:
            videos = task.get_video_materials(
                "task-related",
                params,
                video_terms=["central bank decision"],
                audio_duration=30,
            )

        self.assertEqual(videos, [clip_path])
        related_mock.assert_called_once()
        ytdlp_mock.assert_not_called()
        diagnostics = news_diagnostics.get_task_diagnostics("task-related")
        self.assertEqual(
            [item["event"] for item in diagnostics],
            [
                "news_related_telegram_search_started",
                "news_related_telegram_search_completed",
                "news_material_mix_ready",
            ],
        )

    def test_news_materials_report_non_stock_before_stock_fallback(self):
        story = NewsStory(
            provider="guardian",
            title="Floods force evacuations across coastal city",
            summary="Officials ordered evacuations after heavy rain flooded roads.",
            url="https://example.com/news/floods",
        )
        params = self._params_for_story(story)
        related_path = f"{self.temp_dir.name}/related.mp4"
        stock_path = f"{self.temp_dir.name}/stock.mp4"
        for path in (related_path, stock_path):
            with open(path, "wb") as handle:
                handle.write(b"video")

        with mock.patch.dict(
            "app.services.task.config.app",
            {"news_min_clips": 2, "news_stock_fallback_source": "pexels"},
            clear=False,
        ), mock.patch.object(
            task.news_pipeline,
            "discover_related_telegram_video_materials",
            return_value=[MaterialInfo(provider="telethon", url=related_path, duration=8)],
        ), mock.patch.object(
            task.news_video_search,
            "search_and_download_report",
            return_value=mock.Mock(paths=[], attempts=[]),
        ), mock.patch.object(
            task.material,
            "download_videos",
            return_value=[stock_path],
        ):
            videos = task.get_video_materials(
                "task-mix",
                params,
                video_terms=["coastal flood evacuation"],
                audio_duration=30,
            )

        self.assertEqual(videos, [related_path, stock_path])
        summary = news_diagnostics.get_media_summary("task-mix")
        self.assertEqual(summary["non_stock_paths"], [related_path])
        self.assertEqual(summary["stock_paths"], [stock_path])
        self.assertEqual(summary["stock_video_count"], 1)
        self.assertEqual(summary["stock_needed_count"], 1)
        self.assertEqual(summary["material_order"], "non_stock_before_stock")
        self.assertTrue(summary["stock_fallback_used"])
        self.assertFalse(summary["ready_without_stock"])

    def test_news_script_generation_uses_news_prompt_and_records_diagnostics(self):
        story = NewsStory(
            provider="guardian",
            title="Parliament approves emergency budget",
            summary="Lawmakers approved an emergency budget after a late vote.",
            url="https://example.com/news/1",
        )
        params = self._params_for_story(story)
        params.video_language = "en"
        params.paragraph_number = 2

        with mock.patch.object(
            task.llm,
            "generate_news_script",
            return_value="Parliament approved an emergency budget after a late vote.",
        ) as news_script_mock, mock.patch.object(
            task.llm,
            "generate_script",
        ) as generic_script_mock:
            script = task.generate_script("task-news-script", params)

        self.assertEqual(
            script, "Parliament approved an emergency budget after a late vote."
        )
        news_script_mock.assert_called_once()
        generic_script_mock.assert_not_called()
        diagnostics = news_diagnostics.get_task_diagnostics("task-news-script")
        self.assertEqual(diagnostics[-1]["event"], "news_script_ready")
        self.assertEqual(diagnostics[-1]["properties"]["language"], "en")
        self.assertEqual(
            diagnostics[-1]["properties"]["title"],
            "Parliament approves emergency budget",
        )

    def test_social_publish_preflight_reports_blocked_platforms(self):
        params = VideoParams(
            video_subject="News",
            social_auto_publish=True,
            social_platforms=[SocialPlatform.youtube, SocialPlatform.tiktok],
            tiktok_direct_post_consent=False,
        )

        with mock.patch.object(
            task.youtube_oauth,
            "is_configured",
            return_value=False,
        ), mock.patch.dict(
            "app.services.task.config.app",
            {
                "tiktok_publish_mode": "api",
                "tiktok_upload_enabled": True,
                "social_privacy": "private",
            },
            clear=False,
        ):
            summary, privacy = task._social_publish_preflight(params)

        self.assertEqual(privacy.value, "private")
        self.assertTrue(summary["auto_publish"])
        self.assertEqual(summary["requested_platforms"], ["youtube", "tiktok"])
        self.assertEqual(summary["enabled_platforms"], [])
        self.assertEqual(summary["skip_reason"], "no_enabled_platforms")
        self.assertEqual(
            summary["skipped_platforms"],
            [
                {"platform": "youtube", "reason": "youtube_not_connected"},
                {
                    "platform": "tiktok",
                    "reason": "tiktok_direct_post_consent_missing",
                },
            ],
        )

    def test_social_publish_preflight_reports_disabled_auto_publish(self):
        params = VideoParams(
            video_subject="News",
            social_auto_publish=False,
            social_platforms=[SocialPlatform.youtube],
        )

        summary, _ = task._social_publish_preflight(params)

        self.assertFalse(summary["auto_publish"])
        self.assertEqual(summary["skip_reason"], "auto_publish_disabled")
        self.assertEqual(summary["requested_platforms"], ["youtube"])

    def test_social_publish_preflight_accepts_tiktok_browser_assist(self):
        params = VideoParams(
            video_subject="News",
            social_auto_publish=True,
            social_platforms=[SocialPlatform.tiktok],
        )

        with mock.patch.dict(
            "app.services.task.config.app",
            {
                "tiktok_publish_mode": "browser_assist",
                "tiktok_browser_upload_enabled": True,
                "tiktok_upload_enabled": False,
                "social_privacy": "private",
            },
            clear=False,
        ):
            summary, privacy = task._social_publish_preflight(params)

        self.assertEqual(summary["enabled_platforms"], ["tiktok"])
        self.assertEqual(summary["manual_review_platforms"], ["tiktok"])
        self.assertEqual(summary["skipped_platforms"], [])
        self.assertEqual(privacy.value, "private")

    def test_social_publish_preflight_falls_back_to_tiktok_api_when_browser_assist_disabled(self):
        params = VideoParams(
            video_subject="News",
            social_auto_publish=True,
            social_platforms=[SocialPlatform.tiktok],
            tiktok_direct_post_consent=True,
        )

        with mock.patch.dict(
            "app.services.task.config.app",
            {
                "tiktok_publish_mode": "browser_assist",
                "tiktok_browser_upload_enabled": False,
                "tiktok_upload_enabled": True,
                "social_privacy": "private",
            },
            clear=False,
        ):
            summary, privacy = task._social_publish_preflight(params)

        self.assertEqual(summary["enabled_platforms"], ["tiktok"])
        self.assertEqual(summary.get("manual_review_platforms"), None)
        self.assertEqual(summary["skipped_platforms"], [])
        self.assertEqual(privacy.value, "private")

    def test_social_publish_status_reports_skipped_disabled_publish(self):
        status = task._social_publish_status(
            {
                "auto_publish": False,
                "requested_platforms": ["youtube"],
                "enabled_platforms": [],
                "skipped_platforms": [],
                "skip_reason": "auto_publish_disabled",
                "privacy": "private",
            },
            [],
        )

        self.assertEqual(status["status"], "skipped")
        self.assertEqual(status["reason"], "auto_publish_disabled")
        self.assertEqual(status["result_count"], 0)

    def test_social_publish_status_reports_blocked_preflight(self):
        status = task._social_publish_status(
            {
                "auto_publish": True,
                "requested_platforms": ["youtube", "tiktok"],
                "enabled_platforms": [],
                "skipped_platforms": [
                    {"platform": "youtube", "reason": "youtube_not_connected"}
                ],
                "skip_reason": "no_enabled_platforms",
                "privacy": "private",
            },
            [],
        )

        self.assertEqual(status["status"], "blocked")
        self.assertEqual(status["reason"], "no_enabled_platforms")
        self.assertEqual(status["skipped_platforms"][0]["platform"], "youtube")

    def test_social_publish_status_reports_upload_outcomes(self):
        preflight = {
            "auto_publish": True,
            "requested_platforms": ["youtube", "tiktok"],
            "enabled_platforms": ["youtube", "tiktok"],
            "skipped_platforms": [],
            "privacy": "private",
        }

        uploaded = task._social_publish_status(
            preflight,
            [
                {"platform": "youtube", "success": True},
                {"platform": "tiktok", "success": True},
            ],
        )
        partial = task._social_publish_status(
            preflight,
            [
                {"platform": "youtube", "success": True},
                {"platform": "tiktok", "success": False},
            ],
        )
        failed = task._social_publish_status(
            preflight,
            [
                {"platform": "youtube", "success": False},
                {"platform": "tiktok", "success": False},
            ],
        )

        self.assertEqual(uploaded["status"], "uploaded")
        self.assertEqual(uploaded["success_count"], 2)
        self.assertEqual(partial["status"], "partial")
        self.assertEqual(partial["reason"], "some_platforms_failed")
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["reason"], "all_platforms_failed")

    def test_news_concat_mode_preserves_source_media_order_by_default(self):
        params = VideoParams(
            video_subject="News",
            video_source="news",
            video_concat_mode="random",
        )

        with mock.patch.dict(
            "app.services.task.config.app",
            {"news_preserve_media_order": True},
            clear=False,
        ):
            task._prepare_news_concat_mode("task-order", params, material_count=4)

        self.assertEqual(params.video_concat_mode.value, "sequential")
        diagnostics = news_diagnostics.get_task_diagnostics("task-order")
        self.assertEqual(diagnostics[-1]["event"], "news_media_order_preserved")
        self.assertEqual(diagnostics[-1]["properties"]["material_count"], 4)


if __name__ == "__main__":
    unittest.main()
