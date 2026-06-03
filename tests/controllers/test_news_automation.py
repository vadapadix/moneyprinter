import tempfile
import unittest
from unittest import mock

from app.controllers.v1 import automation
from app.models.schema import NewsAutomationRunRequest, NewsQueryRequest, NewsStory
from app.services import automation as automation_service


class NewsAutomationControllerTest(unittest.TestCase):
    def test_search_news_returns_normalized_stories(self):
        story = NewsStory(
            provider="newsdata",
            title="Market update",
            summary="Stocks moved today",
            url="https://news.example/story",
        )

        with mock.patch.object(automation.news_sources, "search", return_value=[story]):
            response = automation.search_news(
                request=None,
                body=NewsQueryRequest(source="newsdata", query="markets", limit=1),
            )

        self.assertEqual(response["status"], 200)
        self.assertEqual(response["data"]["stories"][0]["provider"], "newsdata")
        self.assertEqual(response["data"]["stories"][0]["title"], "Market update")

    def test_news_automation_queues_story_tasks(self):
        story = NewsStory(
            provider="telethon",
            title="Telegram update",
            summary="A public post",
            url="https://t.me/demo/1",
        )
        added_tasks = []

        with mock.patch.object(
            automation.automation, "prepare_news_run"
        ) as prepare_mock, mock.patch.object(
            automation.video_controller.task_manager, "add_task"
        ) as add_task_mock:
            prepare_mock.return_value = {
                "run_id": "run-1",
                "query": NewsQueryRequest(source="telethon", query="demo", limit=1),
                "stories": [story],
                "tasks": [
                    {
                        "task_id": "task-1",
                        "story": story,
                        "params": automation.automation.build_video_params_from_news(
                            NewsAutomationRunRequest(
                                source="telethon",
                                query="demo",
                                auto_publish=True,
                            ),
                            story,
                        ),
                    }
                ],
            }
            add_task_mock.side_effect = lambda *args, **kwargs: added_tasks.append(
                (args, kwargs)
            )

            response = automation.create_news_automation_run(
                request=None,
                body=NewsAutomationRunRequest(
                    source="telethon",
                    query="demo",
                    auto_publish=True,
                ),
            )

        self.assertEqual(response["status"], 200)
        self.assertEqual(response["data"]["queued_count"], 1)
        self.assertEqual(response["data"]["tasks"][0]["story"]["title"], "Telegram update")
        self.assertEqual(len(added_tasks), 1)
        self.assertEqual(added_tasks[0][0][0], automation._run_news_tasks_sequential)

    def test_news_automation_runs_tasks_sequentially(self):
        first = automation.automation.build_video_params_from_news(
            NewsAutomationRunRequest(source="telethon", query="demo", auto_publish=True),
            NewsStory(
                provider="telethon",
                title="First story",
                summary="First summary",
                url="https://t.me/demo/1",
            ),
        )
        second = automation.automation.build_video_params_from_news(
            NewsAutomationRunRequest(source="telethon", query="demo", auto_publish=True),
            NewsStory(
                provider="telethon",
                title="Second story",
                summary="Second summary",
                url="https://t.me/demo/2",
            ),
        )
        calls = []

        with mock.patch.object(
            automation.tm,
            "start",
            side_effect=lambda task_id, params, stop_at: calls.append(
                (task_id, params.news_source_context["title"], stop_at)
            ),
        ):
            automation._run_news_tasks_sequential(
                [
                    {"task_id": "task-1", "params": first},
                    {"task_id": "task-2", "params": second},
                ]
            )

        self.assertEqual(
            calls,
            [
                ("task-1", "First story", "video"),
                ("task-2", "Second story", "video"),
            ],
        )

    def test_news_video_params_force_english_and_configured_voice(self):
        story = NewsStory(
            provider="telethon",
            title="Українська новина",
            summary="Короткий опис українською",
            url="https://t.me/demo/2",
        )

        with mock.patch.dict(
            "app.services.automation.config.ui",
            {"voice_name": "en-US-BrianNeural-Male", "voice_rate": 1.0},
            clear=False,
        ):
            params = automation_service.build_video_params_from_news(
                NewsAutomationRunRequest(source="telethon", language="uk"),
                story,
            )

        self.assertEqual(params.video_language, "en")
        self.assertEqual(params.voice_name, "en-US-BrianNeural-Male")
        self.assertEqual(params.voice_rate, 1.42)
        self.assertEqual(params.paragraph_number, 3)
        self.assertEqual(params.bgm_type, "news_serious")
        self.assertEqual(params.bgm_volume, 0.08)
        self.assertEqual(params.video_script, "")
        self.assertIn("Write a short factual news voiceover in English", params.video_subject)
        self.assertIn("Українська новина", params.video_subject)

    def test_prepare_news_run_skips_previously_reserved_stories(self):
        used = NewsStory(
            provider="newsdata",
            title="Already used",
            summary="Old summary",
            url="https://news.example/used",
        )
        fresh = NewsStory(
            provider="newsdata",
            title="Fresh story",
            summary="Fresh summary",
            url="https://news.example/fresh",
        )

        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(
            automation_service.news_history.utils,
            "storage_dir",
            lambda sub_dir="", create=False: temp_dir,
        ), mock.patch.object(
            automation_service.news_sources, "search", return_value=[used, fresh]
        ), mock.patch.object(
            automation_service.news_pipeline.web_media,
            "discover_story_media",
            return_value=[],
        ):
            automation_service.news_history.reserve_story(used, run_id="old-run")
            result = automation_service.prepare_news_run(
                NewsAutomationRunRequest(source="newsdata", query="world", limit=1)
            )

        self.assertEqual(len(result["tasks"]), 1)
        self.assertEqual(result["tasks"][0]["story"].title, "Fresh story")

    def test_prepare_news_run_expands_fetch_until_unique_story_is_found(self):
        used = NewsStory(
            provider="guardian",
            title="Already used",
            summary="Old summary",
            url="https://news.example/used",
        )
        fresh = NewsStory(
            provider="guardian",
            title="Fresh article from deeper fetch",
            summary="A detailed new story with enough context for a serious news short.",
            url="https://news.example/fresh-deeper",
        )
        requested_limits = []

        def fake_search(source, query):
            requested_limits.append(query.limit)
            if query.limit <= 3:
                return [used]
            return [used, fresh]

        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(
            automation_service.news_history.utils,
            "storage_dir",
            lambda sub_dir="", create=False: temp_dir,
        ), mock.patch.object(
            automation_service.news_diagnostics.utils,
            "storage_dir",
            lambda sub_dir="", create=False: temp_dir,
        ), mock.patch.dict(
            "app.services.automation.config.app",
            {
                "news_story_fetch_multiplier": 3,
                "news_unique_selection_max_fetch_multiplier": 12,
            },
            clear=False,
        ), mock.patch.object(
            automation_service.news_sources, "search", side_effect=fake_search
        ), mock.patch.object(
            automation_service.news_pipeline.web_media,
            "discover_story_media",
            return_value=[],
        ):
            automation_service.news_history.reserve_story(used, run_id="old-run")
            result = automation_service.prepare_news_run(
                NewsAutomationRunRequest(source="guardian", query="world", limit=1)
            )

        self.assertEqual(result["tasks"][0]["story"].title, fresh.title)
        self.assertEqual(requested_limits[:2], [3, 6])
        self.assertEqual(result["selection_attempts"][0]["selected_count"], 0)
        self.assertEqual(result["selection_attempts"][1]["selected_count"], 1)

    def test_prepare_news_run_ranks_richer_story_before_thin_story(self):
        thin = NewsStory(
            provider="newsdata",
            title="Thin",
            summary="Tiny",
            url="https://news.example/thin",
        )
        rich = NewsStory(
            provider="guardian",
            title="Detailed world update with strong source material",
            summary="A detailed source summary with enough context for a factual English news short. "
            * 3,
            url="https://news.example/rich",
        )

        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(
            automation_service.news_history.utils,
            "storage_dir",
            lambda sub_dir="", create=False: temp_dir,
        ), mock.patch.object(
            automation_service.news_diagnostics.utils,
            "storage_dir",
            lambda sub_dir="", create=False: temp_dir,
        ), mock.patch.object(
            automation_service.news_sources, "search", return_value=[thin, rich]
        ), mock.patch.object(
            automation_service.news_pipeline.web_media,
            "discover_story_media",
            return_value=[],
        ):
            result = automation_service.prepare_news_run(
                NewsAutomationRunRequest(source="auto", query="world", limit=1)
            )

        self.assertEqual(result["tasks"][0]["story"].title, rich.title)
        self.assertGreater(result["ranked_stories"][0]["score"], result["ranked_stories"][1]["score"])


if __name__ == "__main__":
    unittest.main()
