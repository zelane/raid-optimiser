// raid-decoder: decode the game's cached static data (MessagePack + Lz4BlockArray) into raw
// JSON, with the MessagePack build the HellHades install ships.
//
// usage: raid-decoder static [out.json] [static-data-file]
// env:   HH_DIR overrides the extractor install dir its DLLs are loaded from.

using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.Loader;

static class Entry
{
    static string HHDir =>
        Environment.GetEnvironmentVariable("HH_DIR")
        ?? typeof(Entry).Assembly.GetCustomAttributes<AssemblyMetadataAttribute>()
            .First(a => a.Key == "DefaultHHDir").Value!;

    // Must run before anything touches MessagePack types, so the resolver
    // is in place when the JIT first needs those assemblies.
    [ModuleInitializer]
    internal static void InstallResolver()
    {
        AssemblyLoadContext.Default.Resolving += (ctx, name) =>
        {
            var path = Path.Combine(HHDir, name.Name + ".dll");
            return File.Exists(path) ? ctx.LoadFromAssemblyPath(path) : null;
        };
    }

    static int Main(string[] args)
    {
        if (args.Length == 0 || args[0] != "static")
        {
            Console.Error.WriteLine("usage: raid-decoder static [out.json] [static-data-file]");
            return 2;
        }
        if (!Directory.Exists(HHDir))
        {
            Console.Error.WriteLine($"HellHades install not found at {HHDir} (set HH_DIR)");
            return 2;
        }
        try
        {
            return StaticData.Export(args.Length > 2 ? args[2] : null, args.Length > 1 ? args[1] : "static-raw.json", HHDir);
        }
        catch (Exception e)
        {
            Console.Error.WriteLine($"error: {e}");
            return 1;
        }
    }
}
