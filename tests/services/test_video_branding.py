import os
import tempfile
import unittest
from unittest import mock

from app.services import video


class VideoBrandingTest(unittest.TestCase):
    def test_brand_intro_duration_is_capped_by_video_duration(self):
        with mock.patch.dict(
            "app.services.video.config.app",
            {"brand_intro_duration": 2.2},
            clear=False,
        ):
            self.assertEqual(video._brand_intro_duration(1.5), 1.5)
            self.assertEqual(video._brand_intro_duration(10), 2.2)

    def test_brand_intro_duration_can_be_disabled_by_zero(self):
        with mock.patch.dict(
            "app.services.video.config.app",
            {"brand_intro_duration": 0},
            clear=False,
        ):
            self.assertEqual(video._brand_intro_duration(10), 0.0)

    def test_news_serious_bgm_uses_configured_song_subset(self):
        with mock.patch.dict(
            "app.services.video.config.app",
            {"news_serious_bgm_files": ["output004.mp3"]},
            clear=False,
        ), mock.patch.object(video.random, "choice", side_effect=lambda items: items[0]):
            bgm_file = video.get_bgm_file("news_serious")

        self.assertTrue(bgm_file.endswith("output004.mp3"))

    def test_news_serious_bgm_deterministic_strategy_is_stable(self):
        with tempfile.TemporaryDirectory() as song_dir:
            for filename in ("output004.mp3", "output011.mp3", "output015.mp3"):
                with open(os.path.join(song_dir, filename), "wb"):
                    pass

            with mock.patch.object(video.utils, "song_dir", return_value=song_dir), mock.patch.dict(
                "app.services.video.config.app",
                {
                    "news_serious_bgm_strategy": "deterministic",
                    "news_serious_bgm_files": [
                        "output004.mp3",
                        "output011.mp3",
                        "output015.mp3",
                    ],
                },
                clear=False,
            ), mock.patch.object(
                video.random,
                "choice",
                side_effect=AssertionError("deterministic bgm should not use random.choice"),
            ):
                context = {
                    "title": "Major court ruling reshapes election rules",
                    "url": "https://example.test/news/election-ruling",
                    "provider": "guardian",
                }
                first = video.get_bgm_selection("news_serious", context=context)
                second = video.get_bgm_selection("news_serious", context=context)

        self.assertEqual(first["file"], second["file"])
        self.assertEqual(first["strategy"], "news_serious_deterministic")
        self.assertEqual(first["candidate_count"], 3)
        self.assertTrue(first["file"].endswith((".mp3", ".m4a", ".wav", ".aac")))

    def test_brand_watermark_coerces_float_stroke_width_to_int(self):
        class FakeClip:
            w = 120
            h = 32

            def with_duration(self, duration):
                return self

            def with_opacity(self, opacity):
                return self

            def with_position(self, position):
                return self

        captured = {}

        def fake_text_clip(**kwargs):
            captured.update(kwargs)
            return FakeClip()

        with mock.patch.dict(
            "app.services.video.config.app",
            {
                "brand_watermark_enabled": True,
                "brand_watermark_stroke_width": 1.5,
                "brand_watermark_font_size": 34.0,
            },
            clear=False,
        ), mock.patch.object(video, "TextClip", side_effect=fake_text_clip):
            video._create_brand_watermark(1080, 1920, 10)

        self.assertIsInstance(captured["stroke_width"], int)
        self.assertEqual(captured["stroke_width"], 2)
        self.assertIsInstance(captured["font_size"], int)


if __name__ == "__main__":
    unittest.main()
