// raid-export: decode a captured HellHades `api/Account/v2` upload
// (MessagePack + LZ4Block serialized RaidData) into readable JSON.
//
// usage: raid-export <capture.bin> [out-dir]
//        raid-export --selftest [out-dir]
// env:   HH_DIR overrides the extractor install dir used to load HH's DLLs.

using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.Loader;
using System.Text.Json;
using System.Text.Json.Serialization;

static class Entry
{
    static string HHDir =>
        Environment.GetEnvironmentVariable("HH_DIR")
        ?? typeof(Entry).Assembly.GetCustomAttributes<AssemblyMetadataAttribute>()
            .First(a => a.Key == "DefaultHHDir").Value!;

    // Must run before anything touches HH / MessagePack types, so the resolver
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
        if (args.Length == 0)
        {
            Console.Error.WriteLine("usage: raid-export <capture.bin> [out-dir]\n" +
                                    "       raid-export static [out.json] [static-data-file]\n" +
                                    "       raid-export --selftest [out-dir]");
            return 2;
        }
        if (!Directory.Exists(HHDir))
        {
            Console.Error.WriteLine($"HellHades install not found at {HHDir} (set HH_DIR)");
            return 2;
        }
        try
        {
            return args[0] switch
            {
                "--selftest" => Exporter.SelfTest(args.Length > 1 ? args[1] : "selftest-out"),
                "static" => StaticData.Export(args.Length > 2 ? args[2] : null, args.Length > 1 ? args[1] : "static-raw.json", HHDir),
                _ => Exporter.Export(args[0], args.Length > 1 ? args[1] : Path.ChangeExtension(args[0], null)),
            };
        }
        catch (Exception e)
        {
            Console.Error.WriteLine($"error: {e}");
            return 1;
        }
    }
}
