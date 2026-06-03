import os
import tempfile
import types
import unittest
from unittest import mock

from app.services import news_video_search


class FakeYoutubeDL:
    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def extract_info(self, target, download=True):
        self.options.setdefault("targets", []).append(target)
        path = os.path.join(
            os.path.dirname(self.options["outtmpl"]),
            "downloaded-news-video.mp4",
        )
        with open(path, "wb") as handle:
            handle.write(b"video")
        return {
            "entries": [
                {
                    "id": "abc123",
                    "ext": "mp4",
                    "title": "major news headline footage",
                    "requested_downloads": [{"filepath": path}],
                }
            ]
        }

    def prepare_filename(self, entry):
        return os.path.join(os.path.dirname(self.options["outtmpl"]), "fallback.mp4")


class NewsVideoSearchTest(unittest.TestCase):
    def setUp(self):
        self.web_search_config = mock.patch.dict(
            "app.services.news_video_search.config.app",
            {"news_ytdlp_web_search_enabled": False},
            clear=False,
        )
        self.web_search_config.start()

    def tearDown(self):
        self.web_search_config.stop()

    def test_search_and_download_uses_ytdlp_search(self):
        fake_module = types.SimpleNamespace(YoutubeDL=FakeYoutubeDL)
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(
            news_video_search.importlib, "import_module", return_value=fake_module
        ):
            paths = news_video_search.search_and_download(
                "major news headline",
                save_dir=temp_dir,
                limit=1,
            )

        self.assertEqual(len(paths), 1)
        self.assertTrue(paths[0].endswith("downloaded-news-video.mp4"))

    def test_search_and_download_report_tries_source_url_first(self):
        fake_module = types.SimpleNamespace(YoutubeDL=FakeYoutubeDL)
        captured = {}

        class CapturingYoutubeDL(FakeYoutubeDL):
            def __init__(self, options):
                super().__init__(options)
                captured["options"] = options

        fake_module.YoutubeDL = CapturingYoutubeDL
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(
            news_video_search.importlib, "import_module", return_value=fake_module
        ):
            result = news_video_search.search_and_download_report(
                "major news headline",
                save_dir=temp_dir,
                limit=1,
                source_context={"source_url": "https://news.example/story"},
            )

        self.assertEqual(result.paths[0].split(os.sep)[-1], "downloaded-news-video.mp4")
        self.assertEqual(captured["options"]["targets"][0], "https://news.example/story")
        self.assertEqual(result.attempts[0]["kind"], "source_url")

    def test_search_and_download_returns_empty_without_dependency(self):
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(
            news_video_search.importlib,
            "import_module",
            side_effect=ImportError("missing"),
        ):
            paths = news_video_search.search_and_download(
                "major news headline",
                save_dir=temp_dir,
                limit=1,
            )

        self.assertEqual(paths, [])

    def test_search_target_requests_english_news_video(self):
        fake_module = types.SimpleNamespace(YoutubeDL=FakeYoutubeDL)
        captured = {}

        class CapturingYoutubeDL(FakeYoutubeDL):
            def __init__(self, options):
                super().__init__(options)
                captured["options"] = options

        fake_module.YoutubeDL = CapturingYoutubeDL
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(
            news_video_search.importlib, "import_module", return_value=fake_module
        ):
            news_video_search.search_and_download(
                "major news headline",
                save_dir=temp_dir,
                limit=1,
            )

        self.assertEqual(
            captured["options"]["targets"][0],
            "ytsearch1:major news headline English news video",
        )

    def test_search_report_skips_irrelevant_youtube_entries_and_tries_next_variant(self):
        calls = []

        class VariantYoutubeDL(FakeYoutubeDL):
            def extract_info(self, target, download=True):
                calls.append(target)
                dirname = os.path.dirname(self.options["outtmpl"])
                if len(calls) == 1:
                    path = os.path.join(dirname, "wrong.mp4")
                    with open(path, "wb") as handle:
                        handle.write(b"video")
                    return {
                        "entries": [
                            {
                                "title": "cooking show recap",
                                "requested_downloads": [{"filepath": path}],
                            }
                        ]
                    }

                path = os.path.join(dirname, "relevant.mp4")
                with open(path, "wb") as handle:
                    handle.write(b"video")
                return {
                    "entries": [
                        {
                            "title": "major news headline official footage",
                            "requested_downloads": [{"filepath": path}],
                        }
                    ]
                }

        fake_module = types.SimpleNamespace(YoutubeDL=VariantYoutubeDL)
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(
            news_video_search.importlib, "import_module", return_value=fake_module
        ):
            result = news_video_search.search_and_download_report(
                "major news headline",
                save_dir=temp_dir,
                limit=1,
            )

        self.assertTrue(result.paths[0].endswith("relevant.mp4"))
        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(result.attempts[0]["skipped_irrelevant_count"], 1)

    def test_search_report_tries_web_video_pages_when_enabled(self):
        calls = []

        class WebPageYoutubeDL(FakeYoutubeDL):
            def extract_info(self, target, download=True):
                calls.append(target)
                dirname = os.path.dirname(self.options["outtmpl"])
                path = os.path.join(dirname, "web-page-video.mp4")
                with open(path, "wb") as handle:
                    handle.write(b"video")
                return {
                    "title": "major news headline verified footage",
                    "requested_downloads": [{"filepath": path}],
                }

        fake_module = types.SimpleNamespace(YoutubeDL=WebPageYoutubeDL)
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.dict(
            "app.services.news_video_search.config.app",
            {"news_ytdlp_web_search_enabled": True},
            clear=False,
        ), mock.patch.object(
            news_video_search.web_media,
            "search_video_pages",
            return_value=["https://video.example.com/story"],
        ), mock.patch.object(
            news_video_search.importlib, "import_module", return_value=fake_module
        ):
            result = news_video_search.search_and_download_report(
                "major news headline",
                save_dir=temp_dir,
                limit=1,
            )

        self.assertEqual(calls[0], "https://video.example.com/story")
        self.assertTrue(result.paths[0].endswith("web-page-video.mp4"))
        self.assertEqual(result.attempts[0]["kind"], "web_search_url")


if __name__ == "__main__":
    unittest.main()
