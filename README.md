# bmsutils

Helper functions for operating on a Beatoraja database: calculating hashes, moving song folders, merging duplicate folders, etc.

I made these for myself so they're not thoroughly tested. Please check they execute properly. (Worst case you'll need to regenerate your entire bms database.) You can use this as a library or a reference for your own implementation. 

I've written the functions to support both Windows and Linux style paths but I don't have a Linux beatoraja setup to test so it might not work on Linux anyways.

Other tools which may be useful:
 * BMS Sabun import tool: https://note.com/egret_sb/n/nb4f26a6c44ba
 * I made a tool that may speed up beatoraja DB updates (song loading/all song updates) by 256 times https://note.com/3935/n/nb55e8ee5c858

## Installation

 * Python 3.10+ (might rewrite to be compatible with lower versions)
 * No external dependencies
 * Single file so it's easy to use wherever you want

## Functions

 * calculate md5 hash of bms file `bms_hash_md5()` (stress tested, should be correct)
 * calculate sha256 hash of bms file `bms_hash_sha256()` (stress tested, should be correct)
 * calculate crc32 hash of bms folder `bms_path_crc32()` (stress tested, should be correct)
 * (wip) find duplicates
   * (wip) check if a folder is a duplicate
   * (wip) list duplicate bms hashes in the database
 * (wip) merge duplicate bms folders
   * (wip) db only: `db_merge_folder()`
   * (wip) full operation: `merge_folder_plan()` and `merge_folder_execute()`
 * beatoraja songdata.db operations:
   * moving folders
     * db only: `db_move_folder()`
     * full operation: `move_folder()`
   * deleting folders
     * db only: `db_delete_folder()`
     * full operation: `delete_folder()`
   * ~~adding folders~~
     * adding new root folders:
       * db only: `db_add_root_folder()`
       * full operation: `add_root_folder()`
     * this library won't contain any logic to process bms files
     * use Beatoraja to process new bms files and folders
     
## Overview

### Code structure

 * All functions take string paths. The paths have to be formatted with a `/` or `\` as the ending character (e.g.: `C:/my/folder/here/`, `bms\songs\Song Folder\`). This is for compatibility with how paths are stored in `songdata.db`.
   * This is encapsulated by the `BmsPath` alias type and the `bms_path_*` helper functions. Use `bms_path_make` and `check_bms_path` to construct a `BmsPath` type.
   * ~~If you don't like the functional style you can use the `BmsFolder` helper class which wraps the functions as a class.~~ tbd
 * A lot of functions will need the `BmsCrc32Calculator` class, which is a badly named container for some widely used values. Use `BmsCrc32Calculator.from_songdata_db` to construct one of these objects.

### Calculating hashes

```python
# takes file paths
print(bms_hash_md5("another.bms"))
print(bms_hash_sha256("another.bms"))
# or file objects
with open("another.bms", "rb") as fp:
    print(bms_hash_md5(fp))
with open("another.bms", "rb") as fp:
    print(bms_hash_sha256(fp))
```

### Calculating crcs

```python
import sqlite3
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

crc_calc = BmsCrc32Calculator.from_songdata_db(DB_PATH, cursor)
path = bms_path_make("bms/songs/Song Folder", "\\", crc_calc)
print(bms_path_crc32(path, crc_calc))
```

### Moving / deleting / adding folders

**Edge case with root folders**: When manipulating root folders, the list of root folders in `config_sys.json` needs to be modified as well. The `BeatorajaConfig` class is used to support this, which the `move_folder`, `delete_folder` functions take as an argument. If you don't want to modify the config file, then pass None as the argument. (Files will still show up in game even without updating the config file, but the array won't get updated automatically be beatoraja.)

```python
import sqlite3
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

crc_calc = BmsCrc32Calculator.from_songdata_db(DB_PATH, cursor)
config = BeatorajaConfig.load(CONFIG_PATH, crc_calc)

src = bms_path_make("bms/songs/Song Folder", "\\", crc_calc)
dest = bms_path_make("bms/songs_2025/Song Folder", "\\", crc_calc)
db_only = False
if db_only:
    db_move_folder(src, dest, cursor, crc_calc)
else:
    move_folder(src, dest, cursor, crc_calc, config)
```

## Testing

```
python -m unittest discover
python -m unittest tests.test_bms_path
```

**Stress tests**: Set environment variable `TEST_LEVEL = 1` to enable stress tests which for example checks crc calculations against a real songdata.db. (Powershell: `$env:TEST_LEVEL = 1`, Bash: `TEST_LEVEL=1 python -m unittest discover`)

Tests were written with the help of LLMs.
