from bmsutils import BmsPath, LastDirectoryError, db_move_folder

from .sqlite_base import BmsSqliteTestCase


def get_seed_filesystem():
    """Return the base filesystem structure for testing."""
    return {
        "songsA": {
            "bms1": {
                "song1": {
                    "another.bms": "a1b2c3d4",
                },
                "song2": {
                    "hyper.bms": "deadbeef",
                },
            },
            "bms2": {
                "test.bms": "12345678",
            },
        },
        "songsB": {
            "bms3": {
                "normal.bms": "abcdef01",
            },
        },
    }


class TestDbMoveFolder(BmsSqliteTestCase):
    def _seed_database(self):
        pass

    # ===== Basic Move Operations =====

    def test_move_folder_within_same_root(self):
        """Move a folder to a different location within the same root."""
        fs = get_seed_filesystem()
        self.seed_filesystem(fs)

        db_move_folder(
            BmsPath("songsA/bms1/"),
            BmsPath("songsA/bms1_moved/"),
            self.cursor,
            self.crc_calc,
            make_dest_a_root=False,
        )

        # Move bms1 to bms1_moved within songsA
        fs["songsA"]["bms1_moved"] = fs["songsA"].pop("bms1")
        self.assertFilesystem(fs)

    def test_move_folder_to_different_root(self):
        """Move a folder from one root to another root."""
        fs = get_seed_filesystem()
        self.seed_filesystem(fs)

        db_move_folder(
            BmsPath("songsA/bms1/"),
            BmsPath("songsB/bms1/"),
            self.cursor,
            self.crc_calc,
            make_dest_a_root=False,
        )

        # Move bms1 from songsA to songsB
        fs["songsB"]["bms1"] = fs["songsA"].pop("bms1")
        self.assertFilesystem(fs)

    def test_move_folder_with_songs(self):
        """Move a folder containing songs and verify song paths are updated."""
        fs = get_seed_filesystem()
        self.seed_filesystem(fs)

        db_move_folder(
            BmsPath("songsA/bms2/"),
            BmsPath("songsB/bms2_new/"),
            self.cursor,
            self.crc_calc,
            make_dest_a_root=False,
        )

        # Move bms2 from songsA to songsB with new name
        fs["songsB"]["bms2_new"] = fs["songsA"].pop("bms2")
        self.assertFilesystem(fs)

    def test_move_folder_with_subfolders(self):
        """Move a folder with nested subfolders and verify recursive updates."""
        fs = get_seed_filesystem()
        self.seed_filesystem(fs)

        db_move_folder(
            BmsPath("songsA/bms1/"),
            BmsPath("songsB/bms1_moved/"),
            self.cursor,
            self.crc_calc,
            make_dest_a_root=False,
        )

        # Move bms1 (which has subfolders song1 and song2) to songsB
        fs["songsB"]["bms1_moved"] = fs["songsA"].pop("bms1")
        self.assertFilesystem(fs)

    # ===== Root Folder Handling =====

    def test_move_root_folder_with_flag(self):
        """Move a root folder to a new location with make_dest_a_root=True."""
        fs = get_seed_filesystem()
        self.seed_filesystem(fs)

        result = db_move_folder(
            BmsPath("songsA/"),
            BmsPath("songsC/"),
            self.cursor,
            self.crc_calc,
            make_dest_a_root=True,
        )

        # Rename root folder songsA to songsC
        fs["songsC"] = fs.pop("songsA")
        self.assertFilesystem(fs)
        self.assertTrue(result)

    def test_move_root_folder_without_flag(self):
        """Move a root folder without make_dest_a_root flag should raise error."""
        fs = get_seed_filesystem()
        self.seed_filesystem(fs)

        with self.assertRaises(LastDirectoryError):
            db_move_folder(
                BmsPath("songsA/"),
                BmsPath("songsC/"),
                self.cursor,
                self.crc_calc,
                make_dest_a_root=False,
            )

    def test_move_non_root_under_existing_root(self):
        """Move a folder under an existing root becomes non-root even if flag is true."""
        fs = get_seed_filesystem()
        self.seed_filesystem(fs)

        result = db_move_folder(
            BmsPath("songsA/bms1/"),
            BmsPath("songsB/bms1/"),
            self.cursor,
            self.crc_calc,
            make_dest_a_root=True,
        )

        # Move bms1 from songsA to songsB
        fs["songsB"]["bms1"] = fs["songsA"].pop("bms1")
        self.assertFilesystem(fs)
        self.assertFalse(result)

    # ===== Parent Creation =====

    def test_creates_missing_parent_folders(self):
        """Move to a path where intermediate parent folders don't exist."""
        fs = get_seed_filesystem()
        self.seed_filesystem(fs)

        db_move_folder(
            BmsPath("songsA/bms2/"),
            BmsPath("songsA/parent1/parent2/child/"),
            self.cursor,
            self.crc_calc,
            make_dest_a_root=False,
        )

        # Move bms2 deep into nested parents
        bms2_content = fs["songsA"].pop("bms2")
        fs["songsA"]["parent1"] = {"parent2": {"child": bms2_content}}
        self.assertFilesystem(fs)

    # def test_parent_crc_set_correctly(self):
    #     """Verify the moved folder's parent field is set to correct CRC."""
    #     from bmsutils import bms_path_crc32

    #     fs = get_seed_filesystem()
    #     self.seed_filesystem(fs)

    #     db_move_folder(
    #         BmsPath("songsA/bms1/"), BmsPath("songsB/bms1/"), self.cursor, self.crc_calc, make_dest_a_root=False
    #     )

    #     # Check that bms1's parent is now songsB
    #     expected_parent_crc = bms_path_crc32("songsB/", self.crc_calc)
    #     self.cursor.execute("SELECT parent FROM folder WHERE path = ?", ["songsB/bms1/"])
    #     actual_parent_crc = self.cursor.fetchone()[0]
    #     self.assertEqual(expected_parent_crc, actual_parent_crc)

    # ===== Edge Cases =====

    def test_move_empty_folder(self):
        """Move a folder with no songs or subfolders."""

        fs = get_seed_filesystem()
        # Add an empty folder
        fs["songsA"]["empty"] = {}
        self.seed_filesystem(fs)

        db_move_folder(
            BmsPath("songsA/empty/"),
            BmsPath("songsB/empty/"),
            self.cursor,
            self.crc_calc,
            make_dest_a_root=False,
        )

        # Verify the folder was moved
        fs["songsB"]["empty"] = fs["songsA"].pop("empty")
        self.assertFilesystem(fs)

    def test_move_deeply_nested_folder(self):
        """Move a folder that's deeply nested."""

        fs = get_seed_filesystem()
        # Add a deeply nested structure
        fs["songsA"]["bms1"]["level1"] = {}
        fs["songsA"]["bms1"]["level1"]["level2"] = {}
        fs["songsA"]["bms1"]["level1"]["level2"]["level3"] = {}
        fs["songsA"]["bms1"]["level1"]["level2"]["level3"]["level4"] = {"test.bms": "abcdabcd"}

        self.seed_filesystem(fs)

        # Move level2 to a different location
        db_move_folder(
            BmsPath("songsA/bms1/level1/level2/"),
            BmsPath("songsB/level2_moved/"),
            self.cursor,
            self.crc_calc,
            make_dest_a_root=False,
        )

        fs["songsB"]["level2_moved"] = fs["songsA"]["bms1"]["level1"].pop("level2")
        self.assertFilesystem(fs)

    def test_same_source_and_dest(self):
        """Move a folder to itself should be a no-op."""
        fs = get_seed_filesystem()
        self.seed_filesystem(fs)

        before = self.fetch_all()
        db_move_folder(
            BmsPath("songsA/bms1/"),
            BmsPath("songsA/bms1/"),
            self.cursor,
            self.crc_calc,
            make_dest_a_root=False,
        )
        after = self.fetch_all()
        self.assertEqual(before, after)

    # ===== Error Conditions =====

    def test_source_not_in_database(self):
        """Should raise ValueError when source path doesn't exist in database."""
        fs = get_seed_filesystem()
        self.seed_filesystem(fs)

        with self.assertRaises(ValueError) as context:
            db_move_folder(
                BmsPath("nonexistent/path/"),
                BmsPath("songsA/newpath/"),
                self.cursor,
                self.crc_calc,
                make_dest_a_root=False,
            )
        self.assertIn("No entry for folder", str(context.exception))

    def test_no_parent_and_no_root_flag(self):
        """Should raise LastDirectoryError when dest has no ancestor and make_dest_a_root=False."""
        fs = get_seed_filesystem()
        self.seed_filesystem(fs)

        with self.assertRaises(LastDirectoryError) as context:
            db_move_folder(
                BmsPath("songsA/bms1/"),
                BmsPath("newroot/"),
                self.cursor,
                self.crc_calc,
                make_dest_a_root=False,
            )
        self.assertIn("No root folder exists above dest", str(context.exception))

    # def test_multiple_source_entries(self):
    #     """Should raise ValueError when multiple folders with same path exist."""
    #     from bmsutils import bms_path_crc32

    #     fs = get_seed_filesystem()
    #     self.seed_filesystem(fs)

    #     # Insert a duplicate entry
    #     self.cursor.execute(
    #         "INSERT INTO folder VALUES (?, ?, ?)",
    #         ("bms1_duplicate", "songsA/bms1/", bms_path_crc32("songsA/", self.crc_calc)),
    #     )

    #     with self.assertRaises(ValueError) as context:
    #         db_move_folder(
    #             BmsPath("songsA/bms1/"), BmsPath("songsB/bms1/"), self.cursor, self.crc_calc, make_dest_a_root=False
    #         )
    #     self.assertIn("Multiple entries for folder", str(context.exception))

    # ===== Database Consistency =====

    # def test_song_paths_use_relative_structure(self):
    #     """Verify songs' relative paths within folder are preserved."""
    #     fs = get_seed_filesystem()
    #     self.seed_filesystem(fs)

    #     db_move_folder(
    #         BmsPath("songsA/bms1/"), BmsPath("songsB/bms1_moved/"), self.cursor, self.crc_calc, make_dest_a_root=False
    #     )

    #     # Check that the song paths maintain their relative structure
    #     self.cursor.execute("SELECT path FROM song WHERE sha256 = ?", ["a1b2c3d4"])
    #     result = self.cursor.fetchone()
    #     self.assertEqual(result[0], "songsB/bms1_moved/song1/another.bms")

    #     self.cursor.execute("SELECT path FROM song WHERE sha256 = ?", ["deadbeef"])
    #     result = self.cursor.fetchone()
    #     self.assertEqual(result[0], "songsB/bms1_moved/song2/hyper.bms")

    # def test_all_subfolder_parents_updated(self):
    #     """Verify all direct children have their parent CRC updated."""
    #     from bmsutils import bms_path_crc32

    #     fs = get_seed_filesystem()
    #     self.seed_filesystem(fs)

    #     db_move_folder(
    #         BmsPath("songsA/bms1/"), BmsPath("songsB/bms1_moved/"), self.cursor, self.crc_calc, make_dest_a_root=False
    #     )

    #     # Check that song1 and song2's parent is now bms1_moved
    #     expected_parent_crc = bms_path_crc32("songsB/bms1_moved/", self.crc_calc)

    #     self.cursor.execute(
    #         "SELECT parent FROM folder WHERE path = ?", ["songsB/bms1_moved/song1/"]
    #     )
    #     actual_parent_crc = self.cursor.fetchone()[0]
    #     self.assertEqual(expected_parent_crc, actual_parent_crc)

    #     self.cursor.execute(
    #         "SELECT parent FROM folder WHERE path = ?", ["songsB/bms1_moved/song2/"]
    #     )
    #     actual_parent_crc = self.cursor.fetchone()[0]
    #     self.assertEqual(expected_parent_crc, actual_parent_crc)

    # def test_folder_title_updated(self):
    #     """Verify folder's title field is updated to basename of dest."""
    #     fs = get_seed_filesystem()
    #     self.seed_filesystem(fs)

    #     db_move_folder(
    #         BmsPath("songsA/bms1/"),
    #         BmsPath("songsB/bms1_renamed/"),
    #         self.cursor,
    #         self.crc_calc,
    #         make_dest_a_root=False,
    #     )

    #     self.cursor.execute("SELECT title FROM folder WHERE path = ?", ["songsB/bms1_renamed/"])
    #     result = self.cursor.fetchone()
    #     self.assertEqual(result[0], "bms1_renamed")

    # ===== Return Value =====

    def test_returns_true_when_dest_becomes_root(self):
        """Verify function returns True when dest becomes a root folder."""
        fs = get_seed_filesystem()
        self.seed_filesystem(fs)

        result = db_move_folder(
            BmsPath("songsA/bms1/"),
            BmsPath("newroot/"),
            self.cursor,
            self.crc_calc,
            make_dest_a_root=True,
        )
        self.assertTrue(result)

    def test_returns_false_when_dest_not_root(self):
        """Verify function returns False when dest is under an existing root."""
        fs = get_seed_filesystem()
        self.seed_filesystem(fs)

        result = db_move_folder(
            BmsPath("songsA/bms1/"),
            BmsPath("songsB/bms1/"),
            self.cursor,
            self.crc_calc,
            make_dest_a_root=False,
        )
        self.assertFalse(result)
