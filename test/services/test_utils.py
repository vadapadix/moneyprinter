import sys
import types
import unittest
from unittest import mock

from app.utils import utils


class UtilsTest(unittest.TestCase):
    def test_get_ffmpeg_binary_uses_configured_env_path(self):
        with mock.patch.dict("os.environ", {"IMAGEIO_FFMPEG_EXE": "/tmp/custom-ffmpeg"}):
            self.assertEqual(utils.get_ffmpeg_binary(), "/tmp/custom-ffmpeg")

    def test_get_ffmpeg_binary_falls_back_to_imageio_bundle(self):
        fake_imageio_ffmpeg = types.SimpleNamespace(
            get_ffmpeg_exe=lambda: "/tmp/bundled-ffmpeg"
        )
        with (
            mock.patch.dict("os.environ", {}, clear=True),
            mock.patch.object(utils.shutil, "which", return_value=None),
            mock.patch.dict(sys.modules, {"imageio_ffmpeg": fake_imageio_ffmpeg}),
        ):
            self.assertEqual(utils.get_ffmpeg_binary(), "/tmp/bundled-ffmpeg")


if __name__ == "__main__":
    unittest.main()
