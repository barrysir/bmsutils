from bmsutils import db_delete_folder

from .sqlite_base import BmsSqliteTestCase


class TestDbDeleteFolder(BmsSqliteTestCase):
    def _seed_database(self):
        filesystem = {
            "songsA": {
                "bms1": {
                    "another.bms": "a1b2c3d4",
                    "hyper.bms": "deadbeef",
                },
                "bms2": {
                    "test.bms": "12345678",
                },
            },
            "songsB": {
                "bms1": {
                    "another.bms": "a1b2c3d4",
                },
            },
        }
        self.seed_filesystem(filesystem)

    def test_deletes_song_folder(self):
        db_delete_folder("songsA/bms1/", self.cursor, self.crc_calc)
        expected = {
            "songsA": {
                "bms2": {
                    "test.bms": "12345678",
                },
            },
            "songsB": {
                "bms1": {
                    "another.bms": "a1b2c3d4",
                },
            },
        }
        self.assertFilesystem(expected)

    def test_deletes_root_folder(self):
        db_delete_folder("songsA/", self.cursor, self.crc_calc)
        expected = {
            "songsB": {
                "bms1": {
                    "another.bms": "a1b2c3d4",
                },
            },
        }
        self.assertFilesystem(expected)

    def test_no_effect_for_nonexistent_path(self):
        before = self.fetch_all()
        db_delete_folder("does/not/exist/", self.cursor, self.crc_calc)
        after = self.fetch_all()
        self.assertEqual(before, after)

    def test_non_matching_prefix_not_deleted(self):
        before = self.fetch_all()
        db_delete_folder("son/", self.cursor, self.crc_calc)
        after = self.fetch_all()
        self.assertEqual(before, after)
