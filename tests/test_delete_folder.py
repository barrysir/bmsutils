from bmsutils import BmsPath, db_delete_folder

from .sqlite_base import BmsSqliteTestCase


def get_seed_filesystem():
    """Return the base filesystem structure for testing."""
    return {
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


class TestDbDeleteFolder(BmsSqliteTestCase):
    def test_deletes_song_folder(self):
        fs = get_seed_filesystem()
        self.seed_filesystem(fs)

        db_delete_folder(BmsPath("songsA/bms1/"), self.cursor, self.crc_calc)
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
        fs = get_seed_filesystem()
        self.seed_filesystem(fs)

        db_delete_folder(BmsPath("songsA/"), self.cursor, self.crc_calc)
        expected = {
            "songsB": {
                "bms1": {
                    "another.bms": "a1b2c3d4",
                },
            },
        }
        self.assertFilesystem(expected)

    def test_no_effect_for_nonexistent_path(self):
        fs = get_seed_filesystem()
        self.seed_filesystem(fs)
        before = self.fetch_all()
        db_delete_folder(BmsPath("does/not/exist/"), self.cursor, self.crc_calc)
        after = self.fetch_all()
        self.assertEqual(before, after)

    def test_non_matching_prefix_not_deleted(self):
        fs = get_seed_filesystem()
        self.seed_filesystem(fs)
        before = self.fetch_all()
        db_delete_folder(BmsPath("son/"), self.cursor, self.crc_calc)
        after = self.fetch_all()
        self.assertEqual(before, after)
