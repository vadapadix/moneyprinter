import unittest
from unittest import mock

from app.models.schema import NewsQueryRequest
from app.services import news_sources
from app.services.news_sources import get_provider
from app.services.news_sources.guardian import GuardianProvider
from app.services.news_sources.newsdata import NewsDataProvider


class FakeNewsDataResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "results": [
                {
                    "title": "Market update",
                    "description": "Stocks moved today",
                    "link": "https://news.example/story",
                    "pubDate": "2026-05-31 10:00:00",
                    "language": "english",
                    "country": ["us"],
                    "category": ["business"],
                    "keywords": ["markets", "stocks"],
                    "image_url": "https://news.example/image.jpg",
                    "source_id": "example",
                }
            ]
        }


class FakeGuardianResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "response": {
                "results": [
                    {
                        "webTitle": "World update",
                        "webUrl": "https://guardian.example/story",
                        "webPublicationDate": "2026-05-31T08:00:00Z",
                        "sectionName": "World news",
                        "fields": {
                            "trailText": "<p>Important context</p>",
                            "thumbnail": "https://guardian.example/thumb.jpg",
                        },
                    }
                ]
            }
        }


class NewsProviderTest(unittest.TestCase):
    def test_newsdata_provider_normalizes_articles(self):
        with mock.patch.dict(
            "app.services.news_sources.newsdata.config.app",
            {"newsdata_api_key": "key"},
            clear=False,
        ), mock.patch(
            "app.services.news_sources.newsdata.requests.get",
            return_value=FakeNewsDataResponse(),
        ) as get_mock:
            stories = NewsDataProvider().search(
                NewsQueryRequest(query="markets", limit=1)
            )

        self.assertEqual(stories[0].provider, "newsdata")
        self.assertEqual(stories[0].title, "Market update")
        self.assertEqual(stories[0].media[0].media_type, "image")
        self.assertEqual(stories[0].media[0].source_url, "https://news.example/story")
        self.assertEqual(get_mock.call_args.kwargs["params"]["size"], 1)

    def test_guardian_provider_normalizes_articles(self):
        with mock.patch.dict(
            "app.services.news_sources.guardian.config.app",
            {"guardian_api_key": "key"},
            clear=False,
        ), mock.patch(
            "app.services.news_sources.guardian.requests.get",
            return_value=FakeGuardianResponse(),
        ):
            stories = GuardianProvider().search(
                NewsQueryRequest(query="world", country="gb", language="en", limit=1)
            )

        self.assertEqual(stories[0].provider, "guardian")
        self.assertEqual(stories[0].summary, "Important context")
        self.assertEqual(stories[0].media[0].credit, "The Guardian")

    def test_registry_returns_known_provider(self):
        self.assertIsInstance(get_provider("newsdata"), NewsDataProvider)
        self.assertIsInstance(get_provider("guardian"), GuardianProvider)
        self.assertIsNone(get_provider("unknown"))

    def test_auto_source_searches_configured_sources_and_deduplicates(self):
        class FakeProvider:
            def __init__(self, stories):
                self.stories = stories

            def search(self, query):
                return self.stories

        first_story = news_sources.NewsStory(
            provider="newsdata",
            title="Shared story",
            url="https://news.example/shared",
        )
        duplicate_story = news_sources.NewsStory(
            provider="guardian",
            title="Duplicate",
            url="https://news.example/shared",
        )
        fresh_story = news_sources.NewsStory(
            provider="guardian",
            title="Fresh story",
            url="https://guardian.example/fresh",
        )
        providers = {
            "newsdata": FakeProvider([first_story]),
            "guardian": FakeProvider([duplicate_story, fresh_story]),
        }

        with mock.patch.dict(
            "app.services.news_sources.config.app",
            {"news_auto_sources": ["newsdata", "guardian"]},
            clear=False,
        ), mock.patch.object(
            news_sources, "get_provider", lambda source: providers.get(source)
        ):
            stories = news_sources.search(
                "auto", NewsQueryRequest(source="auto", query="world", limit=2)
            )

        self.assertEqual([story.title for story in stories], ["Shared story", "Fresh story"])


if __name__ == "__main__":
    unittest.main()
