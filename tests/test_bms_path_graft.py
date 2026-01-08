import unittest
from unittest.mock import patch

from bmsutils import (
    BmsPath,
    bms_path_graft,
)


class TestBmsPathGraft(unittest.TestCase):
    # ---------- POSIX PATH TESTS ----------

    def test_simple_graft_absolute(self):
        path = BmsPath("/a/b/c/")
        src = BmsPath("/a/")
        dst = BmsPath("/x/")

        result = bms_path_graft(path, src, dst)

        self.assertEqual(result, BmsPath("/x/b/c/"))

    def test_deep_graft_absolute(self):
        path = BmsPath("/a/b/c/d/")
        src = BmsPath("/a/b/")
        dst = BmsPath("/root/")

        result = bms_path_graft(path, src, dst)

        self.assertEqual(result, BmsPath("/root/c/d/"))

    def test_relative_path_graft(self):
        path = BmsPath("a/b/c/")
        src = BmsPath("a/")
        dst = BmsPath("x/")

        result = bms_path_graft(path, src, dst)

        self.assertEqual(result, BmsPath("x/b/c/"))

    def test_graft_when_path_equals_src(self):
        path = BmsPath("/a/b/")
        src = BmsPath("/a/b/")
        dst = BmsPath("/x/")

        result = bms_path_graft(path, src, dst)

        self.assertEqual(result, BmsPath("/x/"))

    # ---------- ASSERTION TESTS ----------

    def test_mixed_absolute_and_relative_raises_assertion(self):
        path = BmsPath("/a/b/")
        src = BmsPath("a/")
        dst = BmsPath("/x/")

        with self.assertRaises(ValueError):
            bms_path_graft(path, src, dst)

    # ---------- WINDOWS PATH TESTS (PLATFORM-INDEPENDENT) ----------

    def test_windows_absolute_graft(self):
        path = BmsPath("C:\\Music\\Artist\\")
        src = BmsPath("C:\\Music\\")
        dst = BmsPath("D:\\Library\\")

        result = bms_path_graft(path, src, dst)

        self.assertEqual(result, BmsPath("D:\\Library\\Artist\\"))
