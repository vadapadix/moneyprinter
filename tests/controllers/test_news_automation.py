import unittest
from unittest import mock

from app.controllers.v1 import automation
from app.models.schema import NewsQueryRequest, NewsStory


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


if __name__ == "__main__":
    unittest.main()
