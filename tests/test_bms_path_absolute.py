import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from bmsutils import (
    BmsPath,
    bms_path_absolute,
)


class TestBmsPathAbsolute(unittest.TestCase):
    def setUp(self):
        self.crc_calc_posix = Mock()
        self.crc_calc_posix.oraja_path = Path("/bms/root")

        self.crc_calc_win = Mock()
        self.crc_calc_win.oraja_path = Path("C:\\bms\\root")

    # ---------- POSIX PATH TESTS ----------

    def test_absolute_posix_path_is_returned_unchanged(self):
        abs_path = BmsPath("/absolute/path/")
        result = bms_path_absolute(abs_path, self.crc_calc_posix)
        self.assertEqual(result, Path(abs_path))

    def test_relative_posix_path_is_joined_with_oraja_path(self):
        rel_path = BmsPath("songs/")
        result = bms_path_absolute(rel_path, self.crc_calc_posix)
        self.assertEqual(result, Path("/bms/root/songs/"))

    # ---------- WINDOWS PATH TESTS ----------

    @patch("os.path.isabs", return_value=True)
    def test_absolute_windows_drive_path(self, mock_isabs):
        win_path = BmsPath("C:\\bms_songs\\songs\\")
        result = bms_path_absolute(win_path, self.crc_calc_win)
        self.assertEqual(result, Path(win_path))

    @patch("os.path.isabs", return_value=True)
    def test_absolute_windows_unc_path(self, mock_isabs):
        win_unc_path = BmsPath("\\\\Server\\Share\\")
        result = bms_path_absolute(win_unc_path, self.crc_calc_win)
        self.assertEqual(result, Path(win_unc_path))

    @patch("os.path.isabs", return_value=False)
    def test_relative_windows_path(self, mock_isabs):
        win_rel_path = BmsPath("songs\\")
        result = bms_path_absolute(win_rel_path, self.crc_calc_win)
        self.assertEqual(result, Path("C:\\bms\\root\\songs"))

    # ---------- EDGE CASES ----------

    def test_empty_relative_path(self):
        rel_path = BmsPath("\\")
        result = bms_path_absolute(rel_path, self.crc_calc_posix)
        self.assertEqual(result, Path("/bms/root"))
