import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.config import config
from app.services import trends


class TestTrends(unittest.TestCase):
    def setUp(self):
        self.original_app_config = dict(config.app)

    def tearDown(self):
        config.app.clear()
        config.app.update(self.original_app_config)

    def test_manual_trends_come_from_config(self):
        config.app["trend_manual_topics"] = ["topic one", "topic two"]

        result = trends.discover_trends(source="manual", region="UA", limit=1)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].topic, "topic one")
        self.assertEqual(result[0].region, "UA")

    def test_youtube_trends_normalize_response(self):
        config.app["youtube_data_api_key"] = "key"
        fake_response = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "items": [
                    {
                        "id": "abc123",
                        "snippet": {"title": "Trending video", "tags": ["one", "two"]},
                        "statistics": {"viewCount": "1234"},
                    }
                ]
            },
        )

        with patch("app.services.trends.requests.get", return_value=fake_response) as get:
            result = trends.discover_trends(source="youtube", region="US", limit=5)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].topic, "Trending video")
        self.assertEqual(result[0].score, 1234.0)
        self.assertIn("chart", get.call_args.kwargs["params"])


if __name__ == "__main__":
    unittest.main()
