import sqlite3
import unittest
from collections import namedtuple
from pathlib import Path

from bmsutils import (
    ROOT_FOLDER_CRC,
    BmsCrc32Calculator,
    BmsPath,
    bms_path_crc32,
    bms_path_dirname,
)

FolderEntry = namedtuple("FolderEntry", ["title", "path", "parent"])
SongEntry = namedtuple("SongEntry", ["sha256", "folder", "path", "parent"])


def fs_to_db_rows(
    fs: dict,
    crc_calc: BmsCrc32Calculator,
) -> tuple[set[FolderEntry], set[SongEntry]]:
    folders = set()
    songs = set()

    def walk(node: dict, current_path: BmsPath, parent_crc: str):
        for name, value in node.items():
            if isinstance(value, dict):
                path = current_path + name + "/"
                folders.add((name, path, parent_crc))
                crc = bms_path_crc32(path, crc_calc)
                walk(value, path, crc)
            else:
                path = current_path + name
                parent_parent_crc = bms_path_crc32(bms_path_dirname(current_path), crc_calc)
                songs.add(
                    (
                        value,
                        parent_crc,
                        path,
                        parent_parent_crc,
                    )
                )

    walk(fs, "", ROOT_FOLDER_CRC)
    return folders, songs


class BmsSqliteTestCase(unittest.TestCase):
    """Base class for tests that require a SQLite database with folder and song tables."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        # self.conn.set_trace_callback(print)
        self.cursor = self.conn.cursor()

        self.cursor.execute("""
            CREATE TABLE `folder` (
               	`title`	TEXT,
               	`subtitle`	TEXT,
               	`command`	TEXT,
               	`path`	TEXT,
               	`banner`	TEXT,
               	`parent`	TEXT,
               	`type`	INTEGER,
               	`date`	INTEGER,
               	`adddate`	INTEGER,
               	`max`	INTEGER,
               	PRIMARY KEY(path)
            );
        """)
        self.cursor.execute("CREATE TABLE song (sha256 TEXT, folder TEXT, path TEXT, parent TEXT)")

        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def seed_filesystem(self, filesystem: dict):
        """Helper method to seed the database with a filesystem structure."""
        self.crc_calc = BmsCrc32Calculator(
            Path("doesntmatter"), [Path(f"{k}") for k in filesystem.keys()]
        )
        self.folders, self.songs = folders, songs = fs_to_db_rows(filesystem, self.crc_calc)
        self.cursor.executemany(
            "INSERT INTO folder VALUES (?, null, null, ?, null, ?, 0, 0, 0, 0)", folders
        )
        self.cursor.executemany("INSERT INTO song VALUES (?, ?, ?, ?)", songs)

    def fetch_all(self):
        """Fetch all data from folder and song tables."""
        return (
            # use set(): the ordering of the records doesn't matter
            set(self.cursor.execute("SELECT title, path, parent FROM folder").fetchall()),
            set(self.cursor.execute("SELECT * FROM song").fetchall()),
        )

    def assertFilesystem(self, fs):
        """Assert that the database matches the expected filesystem structure."""
        expected = fs_to_db_rows(fs, self.crc_calc)
        actual = self.fetch_all()
        self.assertSetEqual(expected[0], actual[0])
        self.assertSetEqual(expected[1], actual[1])
