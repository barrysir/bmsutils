## crc32 function

https://github.com/exch-bms2/beatoraja/blob/17c57c39b9a714ef4b2040100bc0726a04b9ce2a/src/bms/player/beatoraja/song/SongUtils.java#L9

  * bmspath variable
    * "root.toString()" https://github.com/exch-bms2/beatoraja/blob/17c57c39b9a714ef4b2040100bc0726a04b9ce2a/src/bms/player/beatoraja/song/SQLiteSongDatabaseAccessor.java#L448
    * and root comes from Paths.get('.') which refers to the current directory which would be the bms root directory when launching beatoraja. https://github.com/exch-bms2/beatoraja/blob/17c57c39b9a714ef4b2040100bc0726a04b9ce2a/src/bms/player/beatoraja/song/SQLiteSongDatabaseAccessor.java#110
  * rootdirs variable
    * SongUtils.crc32(path.toString(), bmsroot, root.toString()) https://github.com/exch-bms2/beatoraja/blob/17c57c39b9a714ef4b2040100bc0726a04b9ce2a/src/bms/player/beatoraja/song/SQLiteSongDatabaseAccessor.java#L412
    * public BMSFolder(Path path, String[] bmsroot) { https://github.com/exch-bms2/beatoraja/blob/17c57c39b9a714ef4b2040100bc0726a04b9ce2a/src/bms/player/beatoraja/song/SQLiteSongDatabaseAccessor.java#L404
    * BMSFolder folder = new BMSFolder(p, bmsroot); https://github.com/exch-bms2/beatoraja/blob/17c57c39b9a714ef4b2040100bc0726a04b9ce2a/src/bms/player/beatoraja/song/SQLiteSongDatabaseAccessor.java#L372
    * public SongDatabaseUpdater(boolean updateAll, String[] bmsroot, SongInformationAccessor info) {  https://github.com/exch-bms2/beatoraja/blob/17c57c39b9a714ef4b2040100bc0726a04b9ce2a/src/bms/player/beatoraja/song/SQLiteSongDatabaseAccessor.java#L318
    * SongDatabaseUpdater updater = new SongDatabaseUpdater(updateAll, bmsroot, info); https://github.com/exch-bms2/beatoraja/blob/17c57c39b9a714ef4b2040100bc0726a04b9ce2a/src/bms/player/beatoraja/song/SQLiteSongDatabaseAccessor.java#L302
    * public void updateSongDatas(String path, String[] bmsroot, boolean updateAll, SongInformationAccessor info)  https://github.com/exch-bms2/beatoraja/blob/17c57c39b9a714ef4b2040100bc0726a04b9ce2a/src/bms/player/beatoraja/song/SQLiteSongDatabaseAccessor.java#L297
    * getSongDatabase().updateSongDatas(path, config.getBmsroot(), false, getInfoDatabase()); https://github.com/exch-bms2/beatoraja/blob/17c57c39b9a714ef4b2040100bc0726a04b9ce2a/src/bms/player/beatoraja/MainController.java#L813
    * public MainController(Path f, Config config, PlayerConfig player, BMSPlayerMode auto, boolean songUpdated) {  https://github.com/exch-bms2/beatoraja/blob/17c57c39b9a714ef4b2040100bc0726a04b9ce2a/src/bms/player/beatoraja/MainController.java#L126C2-L126C110
    * final MainController main = new MainController(f, config, player, auto, songUpdated); https://github.com/exch-bms2/beatoraja/blob/17c57c39b9a714ef4b2040100bc0726a04b9ce2a/src/bms/player/beatoraja/MainLoader.java#L119
    * if(config == null) { config = Config.read(); } https://github.com/exch-bms2/beatoraja/blob/17c57c39b9a714ef4b2040100bc0726a04b9ce2a/src/bms/player/beatoraja/MainLoader.java#L107
    * Proof `config == null`:
      * public static void play(Path f, BMSPlayerMode auto, boolean forceExit, Config config, PlayerConfig player, boolean songUpdated) {  https://github.com/exch-bms2/beatoraja/blob/17c57c39b9a714ef4b2040100bc0726a04b9ce2a/src/bms/player/beatoraja/MainLoader.java#L105
      * play(bmsPath, auto, true, null, null, bmsPath != null);  https://github.com/exch-bms2/beatoraja/blob/17c57c39b9a714ef4b2040100bc0726a04b9ce2a/src/bms/player/beatoraja/MainLoader.java#L99
    * if (Files.exists(configpath)) { https://github.com/exch-bms2/beatoraja/blob/17c57c39b9a714ef4b2040100bc0726a04b9ce2a/src/bms/player/beatoraja/Config.java#L569
    * static final Path configpath = Paths.get("config_sys.json"); https://github.com/exch-bms2/beatoraja/blob/17c57c39b9a714ef4b2040100bc0726a04b9ce2a/src/bms/player/beatoraja/Config.java#L29
    * and config.getBmsroot() points to the "bmsroot" variable in config_sys.json.

## crc32 inputs

https://github.com/exch-bms2/beatoraja/blob/17c57c39b9a714ef4b2040100bc0726a04b9ce2a/src/bms/player/beatoraja/song/SQLiteSongDatabaseAccessor.java#L479-L491

```java
final String s = (path.startsWith(root) ? root.relativize(path).toString() : path.toString())
	+ File.separatorChar;
// System.out.println("folder更新 : " + s);
Path parentpath = path.getParent();
if(parentpath == null) {
	parentpath = path.toAbsolutePath().getParent();
}
FolderData folder = new FolderData();
folder.setTitle(path.getFileName().toString());
folder.setPath(s);
folder.setParent(SongUtils.crc32(parentpath.toString() , bmsroot, root.toString()));
folder.setDate((int) (Files.getLastModifiedTime(path).toMillis() / 1000));
folder.setAdddate((int) property.updatetime);
```

 * `folder.path` is made relative to the oraja path before adding to database
 * `folder.path` has a trailing `File.separatorChar`, but `folder.parent` doesn't

## Valid BMS extensions

(s.endsWith(".bms") || s.endsWith(".bme") || s.endsWith(".bml") || s.endsWith(".pms") || s.endsWith(".bmson")) https://github.com/exch-bms2/beatoraja/blob/17c57c39b9a714ef4b2040100bc0726a04b9ce2a/src/bms/player/beatoraja/song/SQLiteSongDatabaseAccessor.java#L432-433
