import os
import sys
import tempfile
import unittest
from pathlib import Path

import app


class RuntimeEnvironmentTest(unittest.TestCase):
    def test_runtime_cache_and_temp_paths_stay_in_project_storage(self):
        project_storage = str(app.STORAGE_DIR)
        keys = [
            "TMP",
            "TEMP",
            "TMPDIR",
            "XDG_CACHE_HOME",
            "HF_HOME",
            "HUGGINGFACE_HUB_CACHE",
            "TRANSFORMERS_CACHE",
            "HF_DATASETS_CACHE",
            "TORCH_HOME",
            "MPLCONFIGDIR",
            "PIP_CACHE_DIR",
        ]

        for key in keys:
            with self.subTest(key=key):
                value = os.environ.get(key, "")
                self.assertTrue(value.startswith(project_storage), value)
                self.assertNotEqual(Path(value).drive.upper(), "C:")

        self.assertTrue(tempfile.gettempdir().startswith(project_storage))

    def test_standard_streams_tolerate_unicode_logs_on_windows(self):
        for stream in (sys.stdout, sys.stderr):
            with self.subTest(stream=stream):
                self.assertIn((stream.errors or "").lower(), {"replace", "backslashreplace", "surrogateescape"})


if __name__ == "__main__":
    unittest.main()
