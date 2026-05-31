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
        self.assertEqual(params.video_script, "")
        self.assertIn("Write a short factual news voiceover in English", params.video_subject)
        self.assertIn("Українська новина", params.video_subject)


if __name__ == "__main__":
    unittest.main()
