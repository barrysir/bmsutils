import sqlite3
import unittest

from tqdm import tqdm

import tests.params as params
from bmsutils import BmsCrc32Calculator, bms_path_crc32, bms_path_dirname
from tests.utils import stress_test


class CrcStressTest(unittest.TestCase):
    """Stress test to validate CRC32 calculations against real database"""

    @stress_test
    def test_database_crc32_validation(self):
        """
        Stress test: Read all songs from songdata.db and verify that
        crc32(path.parent) == folder for every row.

        This test requires a real songdata.db file at the specified path.
        Skip if the file doesn't exist.
        """
        db_path = params.DB_PATH

        # Create calculator from the database
        crc_calc = BmsCrc32Calculator.from_songdata_db(db_path)

        # Connect to database and query all songs
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT path, folder FROM song")
            rows = cursor.fetchall()

            total_songs = len(rows)
            self.assertGreater(
                total_songs, 0, "Database should contain at least one song"
            )

            mismatches = []
            already_computed = set()
            for song_path, expected_folder_crc in tqdm(rows):
                # Get the parent directory of the song
                parent_dir = bms_path_dirname(song_path)
                key = (parent_dir, expected_folder_crc)
                if key in already_computed:
                    continue
                already_computed.add(key)

                # Calculate CRC32 of the parent directory
                calculated_crc = bms_path_crc32(parent_dir, crc_calc)

                # Check if it matches the folder field
                if calculated_crc != expected_folder_crc:
                    mismatches.append(
                        {
                            "song_path": song_path,
                            "parent_dir": parent_dir,
                            "expected": expected_folder_crc,
                            "calculated": calculated_crc,
                        }
                    )

                    if len(mismatches) > 10:
                        break

            # Report results
            if mismatches:
                error_msg = f"\nFound {len(mismatches)} mismatches out of {total_songs} songs:\n"
                for i, mismatch in enumerate(mismatches[:10]):  # Show first 10
                    error_msg += (
                        f"\n{i + 1}. Song: {mismatch['song_path']}\n"
                        f"   Parent: {mismatch['parent_dir']}\n"
                        f"   Expected: {mismatch['expected']}\n"
                        f"   Calculated: {mismatch['calculated']}\n"
                    )
                if len(mismatches) > 10:
                    error_msg += f"\n... and {len(mismatches) - 10} more mismatches"

                self.fail(error_msg)

            print(f"\nStress test passed! Validated {total_songs} songs successfully.")

        finally:
            conn.close()
