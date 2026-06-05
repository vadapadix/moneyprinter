import unittest
from unittest import mock

from app.services import news_article


class FakeResponse:
    def __init__(self, text, content_type="text/html"):
        self.text = text
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        return None


class NewsArticleTest(unittest.TestCase):
    def test_fetch_article_text_prefers_json_ld_article_body(self):
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@type":"NewsArticle","articleBody":"The sanctions were announced by the Treasury Department after a formal filing. Officials said the measure targets senior Cuban leadership."}
        </script>
        </head><body><p>Subscribe to our newsletter.</p></body></html>
        """

        with mock.patch.object(
            news_article.requests,
            "get",
            return_value=FakeResponse(html),
        ):
            text = news_article.fetch_article_text("https://news.example/story")

        self.assertIn("Treasury Department", text)
        self.assertNotIn("Subscribe", text)

    def test_fetch_article_text_uses_paragraph_fallback(self):
        html = """
        <html><body>
        <p>The first substantial paragraph gives the core verified fact of the story.</p>
        <p>The second paragraph adds the timeline and people involved in the decision.</p>
        </body></html>
        """

        with mock.patch.object(
            news_article.requests,
            "get",
            return_value=FakeResponse(html),
        ):
            text = news_article.fetch_article_text("https://news.example/story")

        self.assertIn("core verified fact", text)
        self.assertIn("timeline and people involved", text)

    def test_fetch_article_text_can_be_disabled(self):
        with mock.patch.dict(
            "app.services.news_article.config.app",
            {"news_article_text_enabled": False},
            clear=False,
        ), mock.patch.object(news_article.requests, "get") as get_mock:
            text = news_article.fetch_article_text("https://news.example/story")

        self.assertEqual(text, "")
        get_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
