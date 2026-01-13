import sqlite3

from bmsutils import BmsCrc32Calculator, BmsPath, db_merge_folder_execute, db_merge_folder_plan

from .sqlite_base import BmsSqliteTestCase


def db_merge_folder(
    src: BmsPath,
    dest: BmsPath,
    cursor: sqlite3.Cursor,
    crc_calc: BmsCrc32Calculator,
):
    """Combination of db_merge_folder_plan and db_merge_folder_execute used for testing"""
    plan = db_merge_folder_plan(src, dest, cursor, crc_calc)
    db_merge_folder_execute(plan, cursor, crc_calc)


def get_seed_filesystem():
    """Return the base filesystem structure for testing."""
    return {
        "songsA": {
            "src": {
                "file1.bms": "hash1111",
                "file2.bms": "hash2222",
                "file3.bms": "hash3333",
            },
            "dest": {
                "file4.bms": "hash4444",
                "file5.bms": "hash5555",
            },
        },
    }


class TestDbMergeFolder(BmsSqliteTestCase):
    # ===== Basic Merge Operations =====

    def test_merge_folders_with_unique_files(self):
        """Merge src folder containing unique files into dest, verify all files moved."""
        fs = get_seed_filesystem()
        self.seed_filesystem(fs)

        db_merge_folder(BmsPath("songsA/src/"), BmsPath("songsA/dest/"), self.cursor, self.crc_calc)

        # All files from src should be moved to dest, src should be deleted
        fs["songsA"]["dest"].update(fs["songsA"].pop("src"))
        self.assertFilesystem(fs)

    # ===== Duplicate Handling (Same Filename + Same Hash) =====

    def test_merge_with_identical_duplicates(self):
        """Src and dest have same file (same name, same hash), verify duplicate deleted."""
        fs = get_seed_filesystem()
        # Add duplicate file in both folders
        fs["songsA"]["src"]["duplicate.bms"] = "samehash"
        fs["songsA"]["dest"]["duplicate.bms"] = "samehash"
        self.seed_filesystem(fs)

        db_merge_folder(BmsPath("songsA/src/"), BmsPath("songsA/dest/"), self.cursor, self.crc_calc)

        # Src is deleted, duplicate in dest remains (src's copy is deleted)
        fs["songsA"]["src"].pop("duplicate.bms")
        fs["songsA"]["dest"].update(fs["songsA"].pop("src"))

        self.assertFilesystem(fs)

    def test_merge_with_multiple_duplicates(self):
        """Multiple files in src are duplicates of files in dest."""
        fs = get_seed_filesystem()
        # Make file1, file2 exist in both with same hashes
        fs["songsA"]["dest"]["file1.bms"] = "hash1111"
        fs["songsA"]["dest"]["file2.bms"] = "hash2222"
        self.seed_filesystem(fs)

        db_merge_folder(BmsPath("songsA/src/"), BmsPath("songsA/dest/"), self.cursor, self.crc_calc)

        # All duplicates deleted, src deleted
        fs["songsA"]["dest"].update(fs["songsA"].pop("src"))
        self.assertFilesystem(fs)

    def test_all_files_are_duplicates(self):
        """Every file in src is a duplicate, verify all deleted and src removed."""
        fs = get_seed_filesystem()
        # Make all src files duplicates of dest files
        fs["songsA"]["dest"]["file1.bms"] = "hash1111"
        fs["songsA"]["dest"]["file2.bms"] = "hash2222"
        fs["songsA"]["dest"]["file3.bms"] = "hash3333"
        self.seed_filesystem(fs)

        db_merge_folder(BmsPath("songsA/src/"), BmsPath("songsA/dest/"), self.cursor, self.crc_calc)

        # Src deleted, dest unchanged
        del fs["songsA"]["src"]
        self.assertFilesystem(fs)

    # ===== Conflict Detection (Same Filename + Different Hash) =====

    def test_merge_with_conflicting_filename(self):
        """Same filename but different hash should raise error."""
        fs = get_seed_filesystem()
        # Add same filename with different hash
        fs["songsA"]["src"]["conflict.bms"] = "hashAAAA"
        fs["songsA"]["dest"]["conflict.bms"] = "hashBBBB"
        self.seed_filesystem(fs)

        with self.assertRaises(ValueError):
            db_merge_folder(
                BmsPath("songsA/src/"), BmsPath("songsA/dest/"), self.cursor, self.crc_calc
            )

    def test_merge_with_multiple_conflicts(self):
        """Multiple conflicting filenames should report all conflicts."""
        fs = get_seed_filesystem()
        # Multiple conflicts
        fs["songsA"]["src"]["conflict1.bms"] = "hashAAAA"
        fs["songsA"]["dest"]["conflict1.bms"] = "hashBBBB"
        fs["songsA"]["src"]["conflict2.bms"] = "hashCCCC"
        fs["songsA"]["dest"]["conflict2.bms"] = "hashDDDD"
        self.seed_filesystem(fs)

        plan = db_merge_folder_plan(
            BmsPath("songsA/src/"), BmsPath("songsA/dest/"), self.cursor, self.crc_calc
        )
        self.assertGreaterEqual(len(plan.errors), 2)

    def test_execute_rejects_plan_with_errors(self):
        """Execute should raise ValueError when plan has errors."""
        fs = get_seed_filesystem()
        # create a conflict
        fs["songsA"]["src"]["conflict.bms"] = "hashAAAA"
        fs["songsA"]["dest"]["conflict.bms"] = "hashBBBB"
        self.seed_filesystem(fs)

        plan = db_merge_folder_plan(
            BmsPath("songsA/src/"), BmsPath("songsA/dest/"), self.cursor, self.crc_calc
        )
        # plan must have an error
        self.assertGreater(len(plan.errors), 0)
        with self.assertRaises(ValueError):
            db_merge_folder_execute(plan, self.cursor, self.crc_calc)

    # ===== Mixed Scenarios =====

    def test_merge_with_unique_and_duplicates(self):
        """Some files unique, some duplicates, verify correct handling."""
        fs = get_seed_filesystem()
        # file1 is duplicate, file2 and file3 are unique
        fs["songsA"]["dest"]["file1.bms"] = "hash1111"
        self.seed_filesystem(fs)

        db_merge_folder(BmsPath("songsA/src/"), BmsPath("songsA/dest/"), self.cursor, self.crc_calc)

        # file2 and file3 moved, file1 duplicate deleted, src deleted
        fs["songsA"]["dest"]["file2.bms"] = "hash2222"
        fs["songsA"]["dest"]["file3.bms"] = "hash3333"
        del fs["songsA"]["src"]
        self.assertFilesystem(fs)

    def test_merge_with_unique_duplicates_and_conflicts(self):
        """Mix of all three types, verify conflicts prevent execution."""
        fs = get_seed_filesystem()
        # file1 is duplicate (same hash)
        fs["songsA"]["dest"]["file1.bms"] = "hash1111"
        # file2 is unique (only in src)
        # file3 is a conflict (same name, different hash)
        fs["songsA"]["dest"]["file3.bms"] = "differenthash"
        self.seed_filesystem(fs)

        with self.assertRaises(ValueError):
            db_merge_folder(
                BmsPath("songsA/src/"), BmsPath("songsA/dest/"), self.cursor, self.crc_calc
            )

    # ===== Error Conditions =====

    def test_merge_empty_src_into_dest(self):
        """Merge empty src into dest, raises error."""
        fs = get_seed_filesystem()
        fs["songsA"]["src"] = {}  # Empty src
        self.seed_filesystem(fs)

        with self.assertRaises(ValueError):
            db_merge_folder(
                BmsPath("songsA/src/"), BmsPath("songsA/dest/"), self.cursor, self.crc_calc
            )

    def test_merge_src_into_empty_dest(self):
        """Merge src with files into empty dest, raises error."""
        fs = get_seed_filesystem()
        fs["songsA"]["dest"] = {}  # Empty dest
        self.seed_filesystem(fs)

        with self.assertRaises(ValueError):
            db_merge_folder(
                BmsPath("songsA/src/"), BmsPath("songsA/dest/"), self.cursor, self.crc_calc
            )

    def test_merge_two_empty_folders(self):
        """Merge two empty folders, raises error."""
        fs = get_seed_filesystem()
        fs["songsA"]["src"] = {}
        fs["songsA"]["dest"] = {}
        self.seed_filesystem(fs)

        with self.assertRaises(ValueError):
            db_merge_folder(
                BmsPath("songsA/src/"), BmsPath("songsA/dest/"), self.cursor, self.crc_calc
            )

    def test_src_not_in_database(self):
        """Should add error when src path doesn't exist."""
        fs = get_seed_filesystem()
        self.seed_filesystem(fs)

        plan = db_merge_folder_plan(
            BmsPath("songsA/nonexistent/"), BmsPath("songsA/dest/"), self.cursor, self.crc_calc
        )
        self.assertGreater(len(plan.errors), 0)

    def test_dest_not_in_database(self):
        """Should add error when dest path doesn't exist."""
        fs = get_seed_filesystem()
        self.seed_filesystem(fs)

        plan = db_merge_folder_plan(
            BmsPath("songsA/src/"), BmsPath("songsA/nonexistent/"), self.cursor, self.crc_calc
        )
        self.assertGreater(len(plan.errors), 0)

    def test_both_paths_missing(self):
        """Should report both errors."""
        fs = get_seed_filesystem()
        self.seed_filesystem(fs)

        plan = db_merge_folder_plan(
            BmsPath("songsA/missing_src/"),
            BmsPath("songsA/missing_dest/"),
            self.cursor,
            self.crc_calc,
        )

        # Plan should have both errors
        self.assertGreaterEqual(len(plan.errors), 2)

    # ===== Edge Cases =====

    def test_merge_folders_same_path(self):
        """Src and dest are same path should be an error."""
        fs = get_seed_filesystem()
        self.seed_filesystem(fs)
        with self.assertRaises(ValueError):
            db_merge_folder(
                BmsPath("songsA/src/"), BmsPath("songsA/src/"), self.cursor, self.crc_calc
            )

    def test_files_with_different_extensions(self):
        """Test files with same basename but different extensions."""
        fs = get_seed_filesystem()
        fs["songsA"]["src"]["song.bms"] = "hash_bms"
        fs["songsA"]["dest"]["song.bme"] = "hash_bme"
        self.seed_filesystem(fs)

        # These should be treated as different files
        db_merge_folder(BmsPath("songsA/src/"), BmsPath("songsA/dest/"), self.cursor, self.crc_calc)

        # Both should exist in dest
        fs["songsA"]["dest"].update(fs["songsA"].pop("src"))
        self.assertFilesystem(fs)
