import tempfile
import unittest
from unittest import mock

from app.services import news_diagnostics


class NewsDiagnosticsTest(unittest.TestCase):
    def test_record_event_persists_jsonable_events(self):
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(
            news_diagnostics.utils,
            "storage_dir",
            lambda sub_dir="", create=False: temp_dir,
        ):
            news_diagnostics.record_event(
                "task-1",
                "news_story_reserved",
                title="Story",
                paths={"video": "a.mp4"},
            )

            events = news_diagnostics.get_task_diagnostics("task-1")

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "news_story_reserved")
        self.assertEqual(events[0]["properties"]["title"], "Story")


if __name__ == "__main__":
    unittest.main()
