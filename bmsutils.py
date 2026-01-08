from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Generator, Literal, NewType, Optional

# ----------------------------------
# Utility Functions
# ----------------------------------
FpOrPath = str | os.PathLike[str] | io.IOBase
BinaryFpOrPath = str | os.PathLike[str] | io.BufferedIOBase


@contextmanager
def _filepath_or_fileobj(fp_or_path: FpOrPath, *args, **kwds) -> Generator[io.IOBase]:
    """Shared behaviour for functions that can take either a file path or a file object -- open the file path or directly use the file object"""
    if isinstance(fp_or_path, io.IOBase):
        yield fp_or_path
    else:
        with open(fp_or_path, *args, **kwds) as fp:
            yield fp


def _relative_at(rel_or_abs: Path, root: Path):
    """
    Resolve relative paths onto a root path. Do nothing to absolute paths.

    If {rel_or_abs} is absolute, then return {rel_or_abs}
    otherwise return {root} / {rel_or_abs}
    """
    if rel_or_abs.is_absolute():
        return rel_or_abs
    else:
        return root / rel_or_abs


# ----------------------------------
# BMS utility functions
# ----------------------------------
class LastDirectoryError(Exception):
    """Thrown by BmsFolder when it tries to get the parent of a path that doesn't have a parent"""

    pass


def is_root_folder(src: BmsPath, cursor: sqlite3.Cursor):
    """Return whether the given path is a bms root folder by looking up the path in the database."""
    res = cursor.execute("SELECT parent FROM folder WHERE path = ?", (src,))
    record = res.fetchone()
    if record is None:
        raise ValueError(f"Path {src!r} not found in database")
    parent_crc = record[0]
    return parent_crc == ROOT_FOLDER_CRC


# ----------------------------------
# Hashing functions
# ----------------------------------
def bms_hash_md5(fp_or_path: BinaryFpOrPath) -> str:
    "Calculates the bms file md5 hash."
    # Yep, it really is just a hash of the raw file
    with _filepath_or_fileobj(fp_or_path, "rb") as fp:
        return hashlib.file_digest(fp, "md5").hexdigest()


def bms_hash_sha256(fp_or_path: BinaryFpOrPath) -> str:
    "Calculates the bms file sha256 hash."
    # Yep, it really is just a hash of the raw file
    with _filepath_or_fileobj(fp_or_path, "rb") as fp:
        return hashlib.file_digest(fp, "sha256").hexdigest()


def path_to_str(path: Path, sep: Literal["/", "\\"]):
    path_as_str = path.as_posix()
    if sep == "\\":
        path_as_str = path_as_str.replace("/", "\\")
    return path_as_str


# ----------------------------------
# BmsCrc32Calculator
# ----------------------------------
ROOT_FOLDER_CRC = "e2977170"


def crc32(path: str, rootdirs: list[Path], bmspath: Path):
    """
    Calculate the crc32 hash of a folder path, which beatoraja uses to identify folders in its songdata.db database.
    This function needs some other random dependencies so it's easier to use the provided class BmsCrc32Calculator.

    Function directly ported from Java to Python (See DOCUMENTATION.md for research notes)

    path - the folder path (utf-8)
    rootdirs - a list of all your bms directories
    bmspath - path to your bms root directory (e.g. where your beatoraja jar and songdata.db is)
    """
    CRC32_POLYNOMIAL = 0xEDB88320

    def to_absolute(p: Path):
        if p.is_absolute():
            return p
        else:
            return bmspath / p

    path_str = path
    path_p = to_absolute(Path(path))

    for s in rootdirs:
        if to_absolute(s).parent == path_p:
            return "e2977170"

    if path_p.is_relative_to(bmspath):
        # TODO: make sure this uses the right file separator, even though its using Paths and not strings
        path_str = os.path.relpath(path_p, bmspath)

    crc = 0xFFFFFFFF
    for b in (path_str + "\\\0").encode():
        # b in the Java code is type "byte", which is coerced to an int before XORing
        # type "byte" can be negative:
        #   - if b is positive, then coerce to positive int (do nothing)
        #   - if b is negative, then coerce to negative int (two's complement)
        crc ^= ((b - 256) & 0xFFFFFFFF) if b >= 128 else b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ CRC32_POLYNOMIAL
            else:
                crc >>= 1

    # NOTE: do not prefix with 0s to make 8 characters -- there are folders of 7 characters
    return hex(~crc & 0xFFFFFFFF)[2:]  # Strip '0x' and mask to 32-bit unsigned


class BmsCrc32Calculator:
    """Thin wrapper around the crc32() calculation function to manage the dependencies that the crc32 function has"""

    def __init__(self, oraja_path: Path, root_dirs: list[Path]):
        """
        oraja_path - where your beatoraja is installed (same directory as your beatoraja jar, songdata.db)
        root_dirs - a list of all your bms directories
        """
        self.oraja_path = oraja_path
        self.root_dirs = root_dirs

    @classmethod
    def from_songdata_db(
        cls, songdata_db_path: Path, cursor: Optional[sqlite3.Cursor] = None
    ):
        """
        Initialize this class by reading a songdata.db file.

        songdata_db_path -
        """
        if cursor is None:
            conn = sqlite3.connect(songdata_db_path)
            try:
                cursor = conn.cursor()
                return cls.from_songdata_db(songdata_db_path, cursor)
            finally:
                conn.close()

        cursor.execute("SELECT path FROM folder WHERE parent = ?", ("e2977170",))
        root_dirs = [Path(row[0]) for row in cursor.fetchall()]
        oraja_path = songdata_db_path.parent
        return cls(oraja_path, root_dirs)


# ----------------------------------
# BmsPath and helper functions
# ----------------------------------
BmsPath = NewType("BmsPath", str)


def is_absolute(path: BmsPath):
    if path.startswith("/"):
        return True
    return os.path.isabs(path)


def bms_path_make(
    path: Path, separator: Literal["\\", "/"], crc_calc: BmsCrc32Calculator
) -> BmsPath:
    # if path is within the beatoraja directory, change it to a relative path
    if path.is_absolute():
        path = path.resolve()
        if path.is_relative_to(crc_calc.oraja_path):
            path = path.relative_to(crc_calc.oraja_path)
    else:
        # remove any "." or ".." in the path
        root_dir = Path(
            "C:/"
        )  # arbitrary path to serve as a base directory for resolving
        path = (root_dir / path).resolve().relative_to(root_dir)
        if path == Path("."):
            raise ValueError("Invalid path")

    path_as_str = path.as_posix()
    if path_as_str == ".":
        path_as_str = ""
    if separator == "\\":
        path_as_str = path_as_str.replace("/", "\\")
    # add trailing separator
    path_as_str += separator
    return BmsPath(path_as_str)


def bms_path_absolute(path: BmsPath, crc_calc: BmsCrc32Calculator) -> Path:
    if is_absolute(path):
        return Path(path)
    else:
        bms_root = crc_calc.oraja_path
        return bms_root / path[:-1]


def bms_path_crc32(path: BmsPath, crc_calc: BmsCrc32Calculator):
    # The path passed into crc32 doesn't have an ending file separator
    # https://github.com/exch-bms2/beatoraja/blob/17c57c39b9a714ef4b2040100bc0726a04b9ce2a/src/bms/player/beatoraja/song/SQLiteSongDatabaseAccessor.java#L489
    return crc32(path[:-1], crc_calc.root_dirs, crc_calc.oraja_path)


def bms_path_dirname(path: BmsPath):
    sep = path[-1]
    dirname = os.path.dirname(path[:-1])
    if path[:-1] == dirname:
        raise LastDirectoryError("Can't get parent: already at the root directory")
    # if dirname is already root like "/", "\", don't add another slash
    if dirname == sep:
        path = BmsPath(dirname)
    else:
        path = BmsPath(dirname + sep)
    return path


def bms_path_basename(path: BmsPath):
    return os.path.basename(path[:-1])


def bms_path_graft(path: BmsPath, src: BmsPath, dst: BmsPath) -> BmsPath:
    # Make sure compared src paths are either both absolute or relative
    if is_absolute(path) != is_absolute(src):
        raise ValueError(
            "`path` and `src` paths must both be absolute or both be relative"
        )
    relative = path_to_str(Path(path[:-1]).relative_to(Path(src[:-1])), dst[-1])
    if relative == ".":
        return dst
    return BmsPath(dst + relative + dst[-1])


def check_bms_path(path: str) -> BmsPath:
    assert path[-1] in {"\\", "/"}
    return BmsPath(path)


# ----------------------------------
# Folder operations
# ----------------------------------
def db_add_root_folder(folder: str, cursor: sqlite3.Cursor):
    """Create entry for root folder in Beatoraja database if it does not exist."""
    folder = check_bms_path(folder)
    cursor.execute("SELECT * FROM folder WHERE path = ?", [folder])
    folder_row = cursor.fetchall()
    if len(folder_row) == 0:
        parent_crc = ROOT_FOLDER_CRC
        current_time = int(time.time())
        cursor.execute(
            (
                "INSERT INTO folder (title, subtitle, command, path, banner, parent, type, date, adddate, max) "
                "VALUES (:title, :subtitle, :command, :path, :banner, :parent, :type, :date, :adddate, :max) "
            ),
            {
                "title": bms_path_basename(folder),
                "subtitle": "",
                "command": "",
                "path": folder,
                "banner": "",
                "parent": parent_crc,
                "type": 0,
                "date": current_time,
                "adddate": current_time,
                "max": 0,
            },
        )


def db_move_folder(
    src: BmsPath,
    dest: BmsPath,
    cursor: sqlite3.Cursor,
    crc_calc: BmsCrc32Calculator,
):
    """
    Modify the Beatoraja songdata.db database to move the bms folder and bms songs at `src` to `dest`.
     - Checks if `dest` is underneath a root directory
       - If it is, creates any missing parent folder entries for `dest`, between `dest` and its root folder
       - If not, then makes `dest` a new root directory
     - Rewrites the folder entry for `src` to refer to `dest`
     - Modifies child folder entries to point to `dest`
     - Modifies child song entries to point to `dest`
    """

    src = check_bms_path(src)
    dest = check_bms_path(dest)

    def find_and_create_parents(folder: BmsPath):
        """
        Find the closest ancestor of {folder} which exists in the database, and creates any missing parent folder entries in between
        If no ancestor exists in the database, throws an error
        Returns the CRC of the direct parent of {folder}
        """
        rows_to_create: list[tuple[BmsPath, str]] = []
        parent_crc = None

        # search up this folder's parents for an existing entry
        current_folder = folder
        while True:
            try:
                current_folder = bms_path_dirname(current_folder)
            except LastDirectoryError:
                raise LastDirectoryError(
                    "Found no existing folder entry to attach the destination."
                )

            if parent_crc is None:
                parent_crc = bms_path_crc32(current_folder, crc_calc)

            cursor.execute("SELECT * FROM folder WHERE path = ?", [current_folder])
            folder_row = cursor.fetchall()
            if len(folder_row) == 1:
                break
            elif len(folder_row) > 1:
                raise ValueError(
                    f"Multiple entries for folder {current_folder!r} found in database (???)"
                )

            # no entry was found, so remember to create it
            rows_to_create.append(
                (current_folder, bms_path_crc32(current_folder, crc_calc))
            )

        # create all the saved entries
        current_time = int(time.time())
        for create_folder, create_crc in rows_to_create:
            cursor.execute(
                (
                    "INSERT INTO folder (title, subtitle, command, path, banner, parent, type, date, adddate, max) "
                    "VALUES (:title, :subtitle, :command, :path, :banner, :parent, :type, :date, :adddate, :max) "
                ),
                {
                    "title": bms_path_basename(create_folder),
                    "subtitle": "",
                    "command": "",
                    "path": create_folder,
                    "banner": "",
                    "parent": create_crc,
                    "type": 0,
                    "date": current_time,
                    "adddate": current_time,
                    "max": 0,
                },
            )

        return parent_crc

    if src == dest:
        return

    # Make sure there is an entry for this path in the database
    cursor.execute("SELECT parent FROM folder WHERE path = ?", [src])
    folder_row = cursor.fetchall()
    if len(folder_row) == 0:
        raise ValueError(f"No entry for folder {src!r} found in database")
    elif len(folder_row) > 1:
        raise ValueError(f"Multiple entries for folder {src!r} found in database (???)")
    src_crc = bms_path_crc32(src, crc_calc)
    dest_crc = bms_path_crc32(dest, crc_calc)

    # Create parent folder entries
    try:
        dest_parent_crc = find_and_create_parents(dest)
        dest_is_root_folder = False
    except LastDirectoryError:
        dest_parent_crc = ROOT_FOLDER_CRC
        dest_is_root_folder = True

    # Update the current folder entry to point to parent
    cursor.execute(
        (
            "UPDATE folder "
            "SET title = :title, path = :path, parent = :parent "
            "WHERE path = :_search_key"
        ),
        {
            "title": bms_path_basename(dest),
            "path": dest,
            "parent": dest_parent_crc,
            "_search_key": src,
        },
    )

    # Update the folders pointing to this folder
    # dev note: you might think that this can be simplified to a single `UPDATE folder SET parent = (dest_crc) WHERE parent = (src_crc)`,
    #   but the `path` column needs updating too, as well as the songs pointing to the subfolder,
    #   so a full db_move_folder call is necessary
    cursor.execute("SELECT path FROM folder WHERE parent = ?", [src_crc])
    for (path,) in cursor.fetchall():
        sub_src = path
        sub_dest = bms_path_graft(sub_src, src, dest)
        db_move_folder(sub_src, sub_dest, cursor, crc_calc)

    # Update the songs pointing to this folder
    cursor.execute("SELECT path FROM song WHERE folder = ?", [src_crc])
    for (song_path,) in cursor.fetchall():
        # can't use bms_path_graft() here because song_path is a file, not a folder
        song_relative_path = os.path.relpath(song_path, src)
        cursor.execute(
            (
                "UPDATE song "
                "SET folder = :folder, path = :path, parent = :parent "
                "WHERE path = :_search_key"
            ),
            {
                "folder": dest_crc,
                "path": os.path.join(dest, song_relative_path),
                "parent": dest_parent_crc,
                "_search_key": song_path,
            },
        )

    return dest_is_root_folder


def db_delete_folder(src: str, cursor: sqlite3.Cursor, crc_calc: BmsCrc32Calculator):
    """
    Modify the Beatoraja songdata.db database to delete the bms folder and bms songs at {src}.
     - Recursively deletes child folder entries
     - Deletes child song entries
    """

    src = check_bms_path(src)
    src_crc = bms_path_crc32(src, crc_calc)

    # Delete all folders which have src as a parent
    cursor.execute("SELECT path FROM folder WHERE parent = ?", [src_crc])
    for (path,) in cursor.fetchall():
        db_delete_folder(path, cursor, crc_calc)

    # Delete all songs which have src as a parent
    cursor.execute("DELETE FROM song WHERE folder = ?", [src_crc])


def add_root_folder(
    folder: str,
    cursor: sqlite3.Cursor,
    crc_calc: BmsCrc32Calculator,
    config: BeatorajaConfig | None,
):
    folder = check_bms_path(folder)
    folder_abs = bms_path_absolute(folder, crc_calc)
    # make sure the folder doesn't already exist
    assert not folder_abs.exists()

    # add it in the database
    db_add_root_folder(folder, cursor)

    # create the folder on disk
    folder_abs.mkdir(parents=True, exist_ok=True)

    # add it as a bmsroot in the config
    if config is not None:
        config.add_bmsroot(folder)


def move_folder(
    src: str,
    dest: str,
    cursor: sqlite3.Cursor,
    crc_calc: BmsCrc32Calculator,
    config: BeatorajaConfig | None,
):
    src = check_bms_path(src)
    dest = check_bms_path(dest)

    # make sure src exists and dest is empty
    src_abs = bms_path_absolute(src, crc_calc)
    dest_abs = bms_path_absolute(dest, crc_calc)
    assert src_abs.is_dir()
    assert not dest_abs.exists()

    # move folder in the database
    dest_is_root_folder = db_move_folder(src, dest, cursor, crc_calc)

    # move folder on disk
    dest_abs.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(src_abs, dest_abs)

    if config is not None:
        if is_root_folder(src, cursor):
            config.remove_bmsroot(src)
        if dest_is_root_folder:
            config.add_bmsroot(dest)


def _default_send_to_trash(path: Path):
    pass


def delete_folder(
    src: str,
    cursor: sqlite3.Cursor,
    crc_calc: BmsCrc32Calculator,
    config: BeatorajaConfig,
    *,
    send_to_trash: Callable[[Path], Any] = _default_send_to_trash,
):
    src = check_bms_path(src)

    # make sure src exists
    src_abs = bms_path_absolute(src, crc_calc)
    assert src_abs.is_dir()

    # delete folder in the database
    db_delete_folder(src, cursor, crc_calc)

    # delete folder on disk
    send_to_trash(src_abs)

    # delete folder in the beatoraja config file
    if config is not None:
        config.remove_bmsroot(src)


class BeatorajaConfig:
    """Represents the Beatoraja config_sys.json file"""

    def __init__(self, data, crc_calc: BmsCrc32Calculator):
        self.data = data
        self.crc_calc = crc_calc

    @classmethod
    def load(cls, fp_or_path: FpOrPath, crc_calc: BmsCrc32Calculator):
        with _filepath_or_fileobj(fp_or_path, "r", encoding="utf8") as fp:
            data = json.load(fp)
        return cls(data, crc_calc)

    def save(self, fp_or_path):
        with _filepath_or_fileobj(fp_or_path, "w", encoding="utf8") as fp:
            json.dump(self.data, fp)

    def add_bmsroot(self, folder: BmsPath):
        self.data["bmsroot"].append(folder[:-1])

    def remove_bmsroot(self, folder: BmsPath):
        folder_abs = bms_path_absolute(folder, self.crc_calc)

        to_remove = None
        for i, path in enumerate(self.data["bmsroot"]):
            if (
                isinstance(path, str)
                and bms_path_absolute(check_bms_path(path), self.crc_calc) == folder_abs
            ):
                to_remove = i
                break

        if to_remove is not None:
            self.data["bmsroot"].pop(to_remove)
