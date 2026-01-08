import io
import sqlite3
import unittest
from pathlib import Path

from tqdm import tqdm

from bmsutils import bms_hash_md5, bms_hash_sha256
from tests.utils import stress_test


class TestHashing(unittest.TestCase):
    data = (
        Path(__file__).parent / "samples/#be_fortunate[Another].bms",
        "d72fd8244a48425f7a23a0cdfdaf66a2",
        "78cea180d025fc4277722b9f75a317c25e7aafa8aab8f136dfb3aa65ca77806a",
    )

    def test_hash_from_file_path(self):
        path, expected_md5, expected_sha256 = self.data
        with self.subTest("md5"):
            result_md5 = bms_hash_md5(path)
            self.assertEqual(result_md5, expected_md5)
        with self.subTest("sha256"):
            result_sha256 = bms_hash_sha256(path)
            self.assertEqual(result_sha256, expected_sha256)

    def test_hash_from_file_object(self):
        path, expected_md5, expected_sha256 = self.data
        with open(path, "rb") as fp:
            with self.subTest("md5"):
                result_md5 = bms_hash_md5(fp)
                self.assertEqual(result_md5, expected_md5)
            fp.seek(0)
            with self.subTest("sha256"):
                result_sha256 = bms_hash_sha256(fp)
                self.assertEqual(result_sha256, expected_sha256)

    # def test_file_object_position_is_reset_or_ignored(self):
    #     content = b"seek test"
    #     expected = hashlib.md5(content).hexdigest()

    #     fp = io.BytesIO(content)
    #     fp.read()  # advance cursor to EOF

    #     result = bms_hash_md5(fp)
    #     self.assertEqual(result, expected)

    def test_file_object_not_closed(self):
        content = b"do not close me"
        fp = io.BytesIO(content)
        bms_hash_md5(fp)
        self.assertFalse(fp.closed)


class HashStressTest(unittest.TestCase):
    @stress_test
    def test_database_hash_validation(self):
        """
        Stress test: Read all songs from songdata.db and verify that
        the bms hashing functions return the same as the stored database md5 / sha256 hashes for every row.

        This test requires a real songdata.db file at the specified path.
        Skip if the file doesn't exist.
        """
        db_path = test_params.DB_PATH

        # Connect to database and query all songs
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT md5, sha256, path FROM song")
            rows = cursor.fetchall()

            total_songs = len(rows)
            self.assertGreater(
                total_songs, 0, "Database should contain at least one song"
            )

            mismatches = []
            for expected_md5, expected_sha256, song_path in tqdm(rows):
                # store file contents, since we use it twice, once for each hashing algorithm
                with open(song_path, "rb") as fp:
                    bms_contents = io.BytesIO(fp.read())

                if expected_md5 == "":
                    # ignore when the hash in the db is empty (happens for bmson files, which don't have a md5 hash calculated)
                    # make hash pass the equality test
                    md5 = ""
                else:
                    md5 = bms_hash_md5(bms_contents)

                # reset file object to file beginning for next hash
                bms_contents.seek(0)

                if expected_sha256 == "":
                    # ignore when the hash in the db is empty (happens for bmson files, which don't have a md5 hash calculated)
                    # make hash pass the equality test
                    sha256 = ""
                else:
                    sha256 = bms_hash_sha256(bms_contents)

                if md5 != expected_md5 or sha256 != expected_sha256:
                    mismatches.append(
                        {
                            "song_path": song_path,
                            "expected_md5": expected_md5,
                            "expected_sha256": expected_sha256,
                            "calculated_md5": md5,
                            "calculated_sha256": sha256,
                        }
                    )

                    print("Error detected on", song_path, mismatches[-1])

                    if len(mismatches) > 10:
                        break

            # Report results
            if mismatches:
                error_msg = f"\nFound {len(mismatches)} mismatches out of {total_songs} songs:\n"
                for i, mismatch in enumerate(mismatches[:10]):  # Show first 10
                    error_msg += (
                        f"\n{i + 1}. Song: {mismatch['song_path']}\n"
                        f"   Expected md5: {mismatch['expected_md5']}\n"
                        f"   Calculated md5: {mismatch['calculated_md5']}\n"
                        f"   Expected sha256: {mismatch['expected_sha256']}\n"
                        f"   Calculated sha256: {mismatch['calculated_sha256']}\n"
                    )
                if len(mismatches) > 10:
                    error_msg += f"\n... and {len(mismatches) - 10} more mismatches"

                self.fail(error_msg)

            print(f"\nStress test passed! Validated {total_songs} songs successfully.")

        finally:
            conn.close()
