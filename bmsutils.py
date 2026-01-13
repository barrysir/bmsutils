from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import sqlite3
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Generator, Literal, NewType, Optional, cast

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


def _sql_escape_like(string: str, escape: str):
    """
    Escape a string for a SQL LIKE operation.
    NOTE: Must provide the chosen escape character and
    use in SQL with the ESCAPE clause: `WHERE var LIKE '...' ESCAPE (char)`.
    Adding the ESCAPE clause is the only way to escape characters in sqlite.
    """
    # all possible sqlite escape characters: % and _
    # https://www.sqlite.org/lang_expr.html#like

    # escape string must be only 1 character long
    assert len(escape) == 1
    # note - the order is important: the escape character replace must go before the others
    # or it'll double escape those characters
    return (
        string.replace(escape, escape + escape)
        .replace("%", f"{escape}%")
        .replace("_", f"{escape}_")
    )


# ----------------------------------
# BMS utility functions
# ----------------------------------

Separator = Literal["\\", "/"]

# see DOCUMENTATION.md
BMS_EXTENSIONS = {".bms", ".bme", ".bml", ".pms", ".bmson"}


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


def list_bms_files(folder: Path):
    """Return iterator over all bms files in a folder"""
    for file in folder.iterdir():
        if not file.is_file():
            continue

        if file.suffix.lower() in BMS_EXTENSIONS:
            yield file


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


def path_to_str(path: Path, sep: Separator):
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
    def from_songdata_db(cls, songdata_db_path: Path, cursor: Optional[sqlite3.Cursor] = None):
        """
        Initialize this class by reading a songdata.db file.

        songdata_db_path -
            Path to a songdata.db file in a beatoraja installation.
            Used to determine the beatoraja root directory.
        cursor -
            optional open database cursor to the songdata.db file.
            If left empty, function will open its own database connection.
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
BmsFile = NewType("BmsFile", str)


def is_absolute(path: BmsPath):
    if path.startswith("/"):
        return True
    return os.path.isabs(path)


def bms_path_make(path: Path, separator: Separator, crc_calc: BmsCrc32Calculator) -> BmsPath:
    # if path is within the beatoraja directory, change it to a relative path
    if path.is_absolute():
        path = path.resolve()
        if path.is_relative_to(crc_calc.oraja_path):
            path = path.relative_to(crc_calc.oraja_path)
    else:
        # remove any "." or ".." in the path
        root_dir = Path("C:/")  # arbitrary path to serve as a base directory for resolving
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


def bms_path_sep(path: BmsPath) -> Separator:
    """Get the separator used in a bms path"""
    return cast(Separator, path[-1])


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


def bms_path_join(path: BmsPath, filename: str) -> BmsFile:
    return BmsFile(path + filename)


def bms_file_parent(filepath: BmsFile) -> BmsPath:
    if len(filepath) == 0 or filepath[-1] in "/\\":
        raise ValueError(f"argument {filepath} is not a valid filepath")

    i = 2
    for i in range(2, len(filepath)):
        c = filepath[-i]
        if c in "/\\":
            break

    return BmsPath(filepath[: -i + 1])


def bms_path_graft(path: BmsPath, src: BmsPath, dst: BmsPath) -> BmsPath:
    # Make sure compared src paths are either both absolute or relative
    if is_absolute(path) != is_absolute(src):
        raise ValueError("`path` and `src` paths must both be absolute or both be relative")
    relative = path_to_str(Path(path[:-1]).relative_to(Path(src[:-1])), dst[-1])
    if relative == ".":
        return dst
    return BmsPath(dst + relative + dst[-1])


def check_bms_path(path: str) -> BmsPath:
    assert path[-1] in {"\\", "/"}
    return BmsPath(path)


# ----------------------------------
# Find duplicates
# ----------------------------------
def find_duplicate_hashes(cursor: sqlite3.Cursor) -> dict[str, list[BmsFile]]:
    """Return all duplicate hashes in the database."""
    # use sha256 hash instead of the standard md5
    #  - md5 field is blank for bmson files
    # disadvantage: people expect hashes to be md5...
    query = """SELECT sha256,path FROM song INNER JOIN (
        SELECT sha256 FROM song GROUP BY sha256 HAVING COUNT(*) > 1
    ) dt ON dt.sha256 = song.sha256 ORDER BY sha256"""
    dupes = defaultdict(list)
    for row in cursor.execute(query).fetchall():
        dupes[row[0]].append(row[1])
    return dupes


def find_bms_duplicates(bms_path: Path, cursor: sqlite3.Cursor) -> list[BmsFile]:
    """Find all duplicates of a bms file in the database."""
    with open(bms_path, "rb") as fp:
        sha256 = bms_hash_sha256(fp)
    cursor.execute("SELECT path FROM song WHERE sha256 = ?", [sha256])
    return cursor.fetchall()


def find_folder_duplicates(
    song_path: Path, cursor: sqlite3.Cursor, crc_calc: BmsCrc32Calculator
) -> dict[BmsPath, list[tuple[BmsFile, BmsFile]]]:
    """
    Find all folders which are duplicates of the current folder:
    any folders that contain bms files with the same hash as
    a bms file in the current folder.

    Returns `{folder_path: [(path to current folder bms file, path to folder_path bms file)]}`
    """

    folders = defaultdict(list)

    bms_hashes = []
    bms_hash_to_file = {}
    for bms_file in song_path.iterdir():
        if not bms_file.is_file():
            continue

        if bms_file.suffix not in BMS_EXTENSIONS:
            continue

        sha256 = bms_hash_sha256(bms_file)
        bms_hashes.append(sha256)
        bms_hash_to_file[sha256] = bms_file

    query_params = ", ".join("?" for _ in bms_hashes)
    for sha256, dup_path in cursor.execute(
        f"SELECT sha256,path FROM song WHERE sha256 IN ({query_params})", bms_hashes
    ).fetchall():
        folder = bms_file_parent(dup_path)
        src_path = bms_path_make(bms_hash_to_file[sha256], bms_path_sep(folder), crc_calc)
        folders[folder].append((src_path, dup_path))

    # remove the current folder from the results
    current_folder = _relative_at(song_path, crc_calc.oraja_path)
    keys_to_remove = []
    for folder in folders.keys():
        folder_path = bms_path_absolute(folder, crc_calc)
        if current_folder == folder_path:
            keys_to_remove.append(folder)

    for k in keys_to_remove:
        folders.pop(k)

    return dict(folders)


# ----------------------------------
# BeatorajaConfig
# ----------------------------------
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


# ----------------------------------
# Folder operations
# ----------------------------------
def db_add_root_folder(folder: BmsPath, cursor: sqlite3.Cursor):
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
    make_dest_a_root: bool,
):
    """
    Modify the Beatoraja songdata.db database to move the folder at `src` to `dest`.

    `make_dest_a_root` - If you're moving around root folders
    you probably want to set this to true. See below for details.

    What this function does:
     - Checks if `dest` is underneath an existing directory
       - If it is, creates the folder structure from the directory down to `dest`
       - If not, then throws an error
       - If the `make_dest_a_root` flag is on, then sets `dest` to be a root directory.
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
        rows_to_create: list[list] = []
        parent_crc = None

        # search up this folder's parents for an existing entry
        current_folder = folder
        while True:
            try:
                current_folder = bms_path_dirname(current_folder)
                # fill in parent_crc from last row
                if len(rows_to_create) > 0:
                    rows_to_create[-1][1] = bms_path_crc32(current_folder, crc_calc)
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
            rows_to_create.append([current_folder, None])

        # create all the saved entries
        current_time = int(time.time())
        for create_folder, create_parent_crc in rows_to_create:
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
                    "parent": create_parent_crc,
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
    # If dest is below a root folder, then dest has to be a non-root because
    # you can't have a root folder under a root folder
    # Therefore, if dest is below a root folder, set it as a non-root
    # regardless of whether dest was set as a root or not
    # Otherwise, set dest as a root folder if the flag is set, otherwise throw an error
    try:
        dest_parent_crc = find_and_create_parents(dest)
        dest_is_root_folder = False
    except LastDirectoryError:
        if make_dest_a_root:
            dest_parent_crc = ROOT_FOLDER_CRC
            dest_is_root_folder = True
        else:
            raise LastDirectoryError(
                "No root folder exists above dest. "
                "If you intend to place a root folder at dest, use the `make_dest_a_root` flag."
            )

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
        db_move_folder(sub_src, sub_dest, cursor, crc_calc, make_dest_a_root=False)

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


def db_delete_folder(src: BmsPath, cursor: sqlite3.Cursor, crc_calc: BmsCrc32Calculator):
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

    # Delete the current folder
    cursor.execute("DELETE FROM folder WHERE path = ?", [src])


def db_delete_folder_faster(src: BmsPath, cursor: sqlite3.Cursor, crc_calc: BmsCrc32Calculator):
    """
    Modify the Beatoraja songdata.db database to delete the bms folder and bms songs at {src}.
    """

    src = check_bms_path(src)

    # Delete all folders which have src as a parent
    cursor.execute(
        "DELETE FROM folder WHERE path LIKE ? ESCAPE ':'", [_sql_escape_like(src, ":") + "%"]
    )

    # Delete all songs which have src as a parent
    cursor.execute(
        "DELETE FROM song WHERE path LIKE ? ESCAPE ':'", [_sql_escape_like(src, ":") + "%"]
    )


def add_root_folder(
    folder: BmsPath,
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
    src: BmsPath,
    dest: BmsPath,
    cursor: sqlite3.Cursor,
    crc_calc: BmsCrc32Calculator,
    config: BeatorajaConfig | None,
    make_dest_a_root: bool,
):
    src = check_bms_path(src)
    dest = check_bms_path(dest)

    # make sure src exists and dest is empty
    src_abs = bms_path_absolute(src, crc_calc)
    dest_abs = bms_path_absolute(dest, crc_calc)
    assert src_abs.is_dir()
    assert not dest_abs.exists()

    # move folder in the database
    dest_is_root_folder = db_move_folder(
        src, dest, cursor, crc_calc, make_dest_a_root=make_dest_a_root
    )

    # move folder on disk
    dest_abs.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(src_abs, dest_abs)

    if config is not None:
        if is_root_folder(src, cursor):
            config.remove_bmsroot(src)
        if dest_is_root_folder:
            config.add_bmsroot(dest)


def _default_send_to_trash(path: Path):
    shutil.rmtree(path)


def delete_folder(
    src: BmsPath,
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


# ----------------------------------
# Merge operation
# ----------------------------------
@dataclass
class DbMergePlan:
    dest_crc: str
    dest_parent_crc: str
    actions: list[
        tuple[Literal["move"], BmsFile, BmsFile] | tuple[Literal["delete"], list[BmsFile]]
    ]
    errors: Any
    src: BmsPath


@dataclass
class FsMergePlan:
    src: Path
    actions: list[tuple[Literal["move"], Path, Path]]
    errors: Any


def db_merge_folder_plan(
    src: BmsPath,
    dest: BmsPath,
    cursor: sqlite3.Cursor,
    crc_calc: BmsCrc32Calculator,
) -> DbMergePlan:
    src = check_bms_path(src)
    dest = check_bms_path(dest)

    src_crc = bms_path_crc32(src, crc_calc)
    dest_crc = bms_path_crc32(dest, crc_calc)

    actions = []
    errors = []
    errors_per_file: dict[str, list[BmsFile]] = {}
    known_files: dict[str, tuple[str, BmsFile]] = {}
    to_delete: list[BmsFile] = []

    if src_crc == dest_crc:
        errors.append(("Source and dest paths are the same",))

    # safety check: src and dest are both in the database (they are both valid paths)
    if cursor.execute("SELECT parent FROM folder WHERE path = ?", [src]).fetchone() is None:
        errors.append(("Source path wasn't found in database", src))
    if cursor.execute("SELECT parent FROM folder WHERE path = ?", [dest]).fetchone() is None:
        errors.append(("Dest path wasn't found in database", dest))

    # find all songs in both folders
    src_songs = cursor.execute(
        "SELECT sha256, path FROM song WHERE folder = ?", [src_crc]
    ).fetchall()
    dest_songs = cursor.execute(
        "SELECT sha256, path FROM song WHERE folder = ?", [dest_crc]
    ).fetchall()

    # If this error is annoying, I'll turn it into a proper warnings array
    if len(src_songs) == 0:
        errors.append(("Warning: src empty",))
    if len(dest_songs) == 0:
        errors.append(("Warning: dest empty",))

    def process(mode: Literal[0, 1], t: tuple[str, BmsFile]):
        sha256, path = t
        curr_hash = sha256
        filename = Path(path).name
        # precondition - every file in src gets an assigned action / error
        if filename in known_files:
            cached_hash, cached_path = known_files[filename]
            if curr_hash != cached_hash:
                errors_per_file.setdefault(filename, [cached_path]).append(path)
            else:
                to_delete.append(path)
        else:
            if mode == 0:
                known_files[filename] = (curr_hash, path)
            else:
                actions.append(("move", path, bms_path_join(dest, filename)))

    for record in dest_songs:
        process(0, record)
    for record in src_songs:
        process(1, record)

    if len(to_delete) > 0:
        actions.append(("delete", to_delete))

    dest_crc = bms_path_crc32(dest, crc_calc)
    dest_parent_crc = bms_path_crc32(bms_path_dirname(dest), crc_calc)

    for k, v in errors_per_file.items():
        file_hash = known_files[k][0]
        errors.append(("Files have same filename but different hashes", k, file_hash, v))

    return DbMergePlan(
        src=src,
        dest_crc=dest_crc,
        dest_parent_crc=dest_parent_crc,
        actions=actions,
        errors=errors,
    )


def db_merge_folder_execute(
    plan: DbMergePlan, cursor: sqlite3.Cursor, crc_calc: BmsCrc32Calculator
):
    if len(plan.errors) > 0:
        raise ValueError("Preventing merge: merge plan has errors")

    for op in plan.actions:
        if op[0] == "move":
            src_bms = op[1]
            dest_bms = op[2]
            cursor.execute(
                (
                    "UPDATE song "
                    "SET folder = :folder, path = :path, parent = :parent "
                    "WHERE path = :_search_key"
                ),
                {
                    "folder": plan.dest_crc,
                    "path": dest_bms,
                    "parent": plan.dest_parent_crc,
                    "_search_key": src_bms,
                },
            )
        elif op[0] == "delete":
            files = op[1]
            param_array = ", ".join("?" for _ in files)
            cursor.execute(f"DELETE FROM song WHERE path IN ({param_array})", files)

    cursor.execute("DELETE FROM folder WHERE path = ?", [plan.src])


def fs_merge_folder_plan(
    src: BmsPath,
    dest: BmsPath,
    crc_calc: BmsCrc32Calculator,
    safety_level: Literal[0, 1, 2],
) -> FsMergePlan:
    def file_hash(path: Path) -> str:
        with path.open("rb") as f:
            return hashlib.file_digest(f, "sha256").hexdigest()

    actions = []
    errors = []

    src_path: Path = bms_path_absolute(src, crc_calc)
    dest_path: Path = bms_path_absolute(dest, crc_calc)

    if not src_path.is_dir():
        raise ValueError(f"Source is not a directory: {src_path}")

    def recurse(src_dir: Path, dest_dir: Path) -> None:
        for src_path in src_dir.iterdir():
            dest_path = dest_dir / src_path.name

            # Destination does not exist -> move
            if not dest_path.exists():
                actions.append(("move", src_path, dest_path))

            # Both directories -> recurse
            elif src_path.is_dir() and dest_path.is_dir():
                recurse(src_path, dest_path)

            # Both files -> safety checks
            elif src_path.is_file() and dest_path.is_file():
                if safety_level == 1:
                    if src_path.stat().st_size != dest_path.stat().st_size:
                        errors.append((src_path, "File size mismatch"))
                elif safety_level >= 2:
                    if file_hash(src_path) != file_hash(dest_path):
                        errors.append((src_path, "File hash mismatch"))

            # File <-> directory conflict
            else:
                errors.append((src_path, "Type conflict with destination"))

    recurse(src_path, dest_path)
    return FsMergePlan(src_path, actions, errors)


def fs_merge_folders_execute(
    plan: FsMergePlan,
    *,
    send_to_trash: Callable[[Path], Any] = _default_send_to_trash,
):
    if len(plan.errors) > 0:
        raise ValueError("Preventing merge: merge plan has errors")

    for action in plan.actions:
        if action[0] == "move":
            src = action[1]
            dest = action[2]
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(src, dest)

    send_to_trash(plan.src)


def merge_folders_plan(
    src: BmsPath,
    dest: BmsPath,
    cursor: sqlite3.Cursor,
    crc_calc: BmsCrc32Calculator,
    safety_level: Literal[0, 1, 2],
):
    db_plan = db_merge_folder_plan(src, dest, cursor, crc_calc)
    fs_plan = fs_merge_folder_plan(src, dest, crc_calc, safety_level)
    return db_plan, fs_plan


def merge_folders_execute(plan, cursor: sqlite3.Cursor, crc_calc: BmsCrc32Calculator):
    db_plan, fs_plan = plan
    if len(db_plan.errors) > 0 or len(fs_plan.errors) > 0:
        raise ValueError("Preventing merge: merge plan has errors")

    db_merge_folder_execute(db_plan, cursor, crc_calc)
    fs_merge_folders_execute(fs_plan)
