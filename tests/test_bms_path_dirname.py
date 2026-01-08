import unittest

from bmsutils import (
    BmsPath,
    LastDirectoryError,
    bms_path_dirname,
)


class TestBmsPathDirname(unittest.TestCase):
    # ---------- POSIX PATH TESTS ----------

    def test_simple_directory(self):
        path = BmsPath("/songs/")
        result = bms_path_dirname(path)
        self.assertEqual(result, BmsPath("/"))

    def test_nested_directory(self):
        path = BmsPath("/songs/artist/album/")
        result = bms_path_dirname(path)
        self.assertEqual(result, BmsPath("/songs/artist/"))

    def test_relative_directory(self):
        path = BmsPath("songs/artist/")
        result = bms_path_dirname(path)
        self.assertEqual(result, BmsPath("songs/"))

    def test_relative_single_directory(self):
        path = BmsPath("songs/")
        result = bms_path_dirname(path)
        self.assertEqual(result, BmsPath("/"))

    # ---------- WINDOWS-LIKE PATH TESTS ----------

    def test_windows_style_path(self):
        path = BmsPath("C:\\Music\\Artist\\")
        result = bms_path_dirname(path)
        self.assertEqual(result, BmsPath("C:\\Music\\"))

    def test_windows_root_raises(self):
        path = BmsPath("C:\\")
        with self.assertRaises(LastDirectoryError):
            bms_path_dirname(path)

    # ---------- EDGE CASES ----------

    def test_root_directory_raises(self):
        path = BmsPath("/")
        with self.assertRaises(LastDirectoryError):
            bms_path_dirname(path)

    def test_trailing_separator_preserved(self):
        path = BmsPath("/a/b/c/")
        result = bms_path_dirname(path)
        self.assertTrue(result.endswith(path[-1]))
