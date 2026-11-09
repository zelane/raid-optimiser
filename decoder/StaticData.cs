using MessagePack;

// Converts the game's cached static data (MessagePack, Lz4BlockArray, string keys)
// to raw JSON. Key renaming/typing happens in tools/static_export.py using a
// schema generated from the IL2CPP dump.
static class StaticData
{
    const string CacheRel = "users/steamuser/AppData/LocalLow/Plarium/Raid_ Shadow Legends/static-data";

    public static int Export(string? input, string outPath, string hhDir)
    {
        var file = input ?? FindNewest(hhDir);
        var opts = MessagePackSerializerOptions.Standard.WithCompression(MessagePackCompression.Lz4BlockArray);
        var json = MessagePackSerializer.ConvertToJson(File.ReadAllBytes(file), opts);
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(outPath))!);
        File.WriteAllText(outPath, json);
        // Game version is the parent folder name (static-data/<version>/<hash>).
        Console.WriteLine($"static data {Path.GetFileName(Path.GetDirectoryName(file))} ({new FileInfo(file).Length} bytes) -> {Path.GetFullPath(outPath)}");
        return 0;
    }

    // The game's cache is under <prefix>/drive_c: RAID_PREFIX names the prefix, else HHDir is
    // taken to be <prefix>/drive_c/hh.
    static string FindNewest(string hhDir)
    {
        var prefix = Environment.GetEnvironmentVariable("RAID_PREFIX");
        var driveC = prefix != null
            ? Path.Combine(prefix, "drive_c")
            : Path.GetDirectoryName(Path.GetFullPath(hhDir))!;
        var root = Path.Combine(driveC, CacheRel);
        var newest = Directory.Exists(root)
            ? Directory.EnumerateFiles(root, "*", SearchOption.AllDirectories)
                .OrderByDescending(File.GetLastWriteTimeUtc).FirstOrDefault()
            : null;
        return newest ?? throw new FileNotFoundException($"no cached static data under {root}; pass the file explicitly");
    }
}
