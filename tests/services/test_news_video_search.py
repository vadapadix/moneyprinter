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
                    "requested_downloads": [{"filepath": path}],
                }
            ]
        }

    def prepare_filename(self, entry):
        return os.path.join(os.path.dirname(self.options["outtmpl"]), "fallback.mp4")


class NewsVideoSearchTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
