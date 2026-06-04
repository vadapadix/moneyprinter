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

    def test_verify_output_video_file_returns_file_size(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as output:
            output.write(b"video")
            output_path = output.name

        try:
            self.assertEqual(video._verify_output_video_file(output_path), 5)
        finally:
            os.remove(output_path)

    def test_verify_output_video_file_rejects_missing_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "missing.mp4")
            with self.assertRaisesRegex(RuntimeError, "was not written"):
                video._verify_output_video_file(output_path)

    def test_verify_output_video_file_rejects_empty_file(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as output:
            output_path = output.name

        try:
            with self.assertRaisesRegex(RuntimeError, "is empty"):
                video._verify_output_video_file(output_path)
        finally:
            os.remove(output_path)

    def test_moviepy_render_logger_reports_progress_without_spam(self):
        render_logger = video._MoviePyRenderLogger(
            "final.mp4",
            min_interval_seconds=999,
        )

        with mock.patch.object(video.logger, "info") as info_mock:
            render_logger(frame__total=100)
            render_logger(frame__index=0)
            render_logger(frame__index=1)
            render_logger(frame__index=100)

        self.assertEqual(info_mock.call_count, 2)
        self.assertIn("progress=0/100 (0.0%)", info_mock.call_args_list[0].args[0])
        self.assertIn("progress=100/100 (100.0%)", info_mock.call_args_list[1].args[0])

    def test_moviepy_render_logger_uses_configured_interval(self):
        with mock.patch.dict(
            "app.services.video.config.app",
            {"moviepy_render_progress_interval_seconds": "2.5"},
            clear=False,
        ):
            render_logger = video._moviepy_render_logger("final.mp4")

        self.assertEqual(render_logger.min_interval_seconds, 2.5)


if __name__ == "__main__":
    unittest.main()
