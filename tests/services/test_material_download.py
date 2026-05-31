import unittest

from app.services import material


class MaterialDownloadTest(unittest.TestCase):
    def test_download_videos_ignores_error_string_terms(self):
        result = material.download_videos(
            task_id="task-1",
            search_terms="Error: 429 quota exceeded",
            audio_duration=1,
        )

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
