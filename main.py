import sqlite3
from pathlib import Path

from bmsutils import (
    BeatorajaConfig,
    BmsCrc32Calculator,
    bms_path_make,
    db_move_folder,
    move_folder,
)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Move bms songs in one folder to another folder."
    )

    parser.add_argument("root", type=Path, help="beatoraja path")
    parser.add_argument("src", type=Path, help="Source path")
    parser.add_argument("dest", type=Path, help="Destination path")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )

    args = parser.parse_args()

    DB_PATH = args.root / "songdata.db"
    CONFIG_PATH = args.root / "config_sys.json"

    conn = sqlite3.connect(DB_PATH, autocommit=False)
    conn.set_trace_callback(print)
    cursor = conn.cursor()

    crc_calc = BmsCrc32Calculator.from_songdata_db(DB_PATH, cursor)
    config = BeatorajaConfig.load(CONFIG_PATH, crc_calc)

    try:
        with conn:
            for folder in args.src.iterdir():
                if not folder.is_dir():
                    continue

                src = folder
                dest = args.dest / folder.name
                src = bms_path_make(src, "\\", crc_calc)
                dest = bms_path_make(dest, "\\", crc_calc)

                print("Moving", src, dest)
                if args.dry_run:
                    db_move_folder(src, dest, cursor, crc_calc)
                else:
                    move_folder(src, dest, cursor, crc_calc, config)

            if args.dry_run:
                raise RuntimeError("Dry run")
            config.save(CONFIG_PATH)
    finally:
        conn.close()
