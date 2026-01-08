import unittest
from pathlib import Path, PureWindowsPath
from unittest.mock import Mock

from bmsutils import BmsPath, bms_path_make


class TestBmsPathMake(unittest.TestCase):
    def setUp(self):
        self.crc_calc = Mock()
        self.crc_calc.oraja_path = Path("C:/Beatoraja")

    # ---------- ABSOLUTE PATHS INSIDE ORAJA ----------

    def test_windows_absolute_path_inside_oraja_becomes_relative(self):
        path = Path("C:/Beatoraja/Songs/Artist")
        result = bms_path_make(path, "\\", self.crc_calc)
        self.assertEqual(result, BmsPath("Songs\\Artist\\"))

    def test_windows_absolute_path_equal_to_oraja_root(self):
        path = Path("C:/Beatoraja")
        result = bms_path_make(path, "\\", self.crc_calc)
        self.assertEqual(result, BmsPath("\\"))

    # ---------- ABSOLUTE PATHS OUTSIDE ORAJA ----------

    def test_windows_absolute_path_outside_oraja_remains_absolute(self):
        path = Path("D:/Music/BMS")
        result = bms_path_make(path, "\\", self.crc_calc)
        self.assertEqual(result, BmsPath("D:\\Music\\BMS\\"))

    def test_windows_absolute_path_directory_traversal(self):
        path = Path("D:/Music/BMS/Test/Name/../../Songs")
        result = bms_path_make(path, "\\", self.crc_calc)
        self.assertEqual(result, BmsPath("D:\\Music\\BMS\\Songs\\"))

    # ---------- RELATIVE WINDOWS PATHS ----------

    def test_windows_relative_path(self):
        path = Path(PureWindowsPath("Songs\\Artist"))
        result = bms_path_make(path, "\\", self.crc_calc)
        self.assertEqual(result, BmsPath("Songs\\Artist\\"))

    def test_windows_relative_single_directory(self):
        path = Path(PureWindowsPath("Songs"))
        result = bms_path_make(path, "\\", self.crc_calc)
        self.assertEqual(result, BmsPath("Songs\\"))

    def test_windows_unresolved_directory(self):
        path = Path(PureWindowsPath("Songs") / "Artist" / "Test" / ".." / "Test2")
        result = bms_path_make(path, "\\", self.crc_calc)
        self.assertEqual(result, BmsPath("Songs\\Artist\\Test2\\"))

    def test_windows_current_directory(self):
        path = Path(PureWindowsPath("."))
        with self.assertRaises(ValueError):
            bms_path_make(path, "\\", self.crc_calc)

    def test_windows_up_directory(self):
        path = Path(PureWindowsPath(".."))
        with self.assertRaises(ValueError):
            bms_path_make(path, "\\", self.crc_calc)

    # ---------- SEPARATOR BEHAVIOR ----------

    def test_windows_separator_always_used(self):
        path = Path("C:/Beatoraja/Songs/Artist")
        result = bms_path_make(path, "\\", self.crc_calc)
        self.assertNotIn("/", result)
        self.assertTrue(result.endswith("\\"))

    def test_posix_separator_with_windows_path(self):
        path = Path("C:/Beatoraja/Songs/Artist")
        result = bms_path_make(path, "/", self.crc_calc)
        self.assertEqual(result, BmsPath("Songs/Artist/"))
