using System.Text.Json;
using System.Text.Json.Serialization;
using HellHades.ArtifactExtractor.Models;
using MessagePack;

// Kept separate from Entry so HH/MessagePack types are only JIT-resolved
// after the assembly resolver has been installed.
static class Exporter
{
    // Identical to what the extractor uses in RaidDataUpdatedEventHandler.
    static readonly MessagePackSerializerOptions Mp =
        MessagePackSerializerOptions.Standard.WithCompression(MessagePackCompression.Lz4Block);

    static readonly JsonSerializerOptions Json = new()
    {
        WriteIndented = true,
        Converters = { new JsonStringEnumConverter() },
        ReferenceHandler = ReferenceHandler.IgnoreCycles,
        NumberHandling = JsonNumberHandling.AllowNamedFloatingPointLiterals,
    };

    public static int Export(string capturePath, string outDir)
    {
        var data = MessagePackSerializer.Deserialize<RaidData>(File.ReadAllBytes(capturePath), Mp);
        Write(data, outDir);
        return 0;
    }

    public static int SelfTest(string outDir)
    {
        // Round-trip a synthetic account through HH's own serializer to prove the
        // pipeline (resolver, LZ4, MessagePack, JSON) without a real capture.
        var data = new RaidData
        {
            Name = "selftest",
            HeroTypes = { new HeroType { Id = 1236, Name = "Test Champion", Rarity = Rarity.Legendary } },
            Heroes = { new Hero { Id = 1, TypeId = 1236, Level = 60, Grade = Grade.SixStars, Artifacts = new() { 10, 11 } } },
        };
        var bytes = MessagePackSerializer.Serialize(data, Mp);
        var back = MessagePackSerializer.Deserialize<RaidData>(bytes, Mp);
        Write(back, outDir);
        File.WriteAllBytes(Path.Combine(outDir, "selftest.bin"), bytes);
        Console.WriteLine($"selftest ok ({bytes.Length} bytes round-tripped)");
        return 0;
    }

    static void Write(RaidData data, string outDir)
    {
        Directory.CreateDirectory(outDir);
        var types = data.HeroTypes.Count > 0
            ? data.HeroTypes.GroupBy(t => t.Id).ToDictionary(g => g.Key, g => g.First())
            : HeroTypes.Load(HeroTypeCachePath, data.Heroes.Select(h => h.TypeId).Distinct());

        var champions = data.Heroes
            .Select(h =>
            {
                types.TryGetValue(h.TypeId, out var t);
                var form = t?.Forms?.FirstOrDefault();
                return new
                {
                    h.Id,
                    h.TypeId,
                    Name = t?.Name,
                    Faction = t?.Fraction,
                    Rarity = t?.Rarity,
                    Element = form?.Element,
                    Role = form?.Role,
                    h.Grade,
                    h.AwakenedGrade,
                    h.Level,
                    h.EmpowerLevel,
                    h.Locked,
                    h.InStorage,
                    h.InBathhouse,
                    h.Marker,
                    h.BlessingId,
                    h.SkillLevels,
                    h.Masteries,
                    h.Artifacts,
                    h.Relics,
                };
            })
            .OrderByDescending(c => c.Rarity).ThenByDescending(c => c.Grade).ThenByDescending(c => c.Level).ThenBy(c => c.Name)
            .ToList();

        Dump(outDir, "account.json", data);
        Dump(outDir, "champions.json", champions);
        Dump(outDir, "artifacts.json", data.Artifacts);
        // HH names sets its own way; their numbers match the game's ArtifactSetKindId.
        var setEnum = typeof(Artifact).GetProperty(nameof(Artifact.Set))!.PropertyType;
        Dump(outDir, "set_ids.json", Enum.GetValues(setEnum).Cast<object>()
            .ToDictionary(v => v.ToString()!, v => Convert.ToInt32(v)));

        var unnamed = champions.Count(c => c.Name == null);
        Console.WriteLine($"{data.Name}: {champions.Count} champions ({unnamed} unnamed), {data.Artifacts.Count} artifacts, " +
                          $"{data.Relics.Count} relics -> {Path.GetFullPath(outDir)}");
    }

    // raid-optimiser/data/cache/hero_types.json (the binary lives in raid-optimiser/bin/).
    static string HeroTypeCachePath =>
        Environment.GetEnvironmentVariable("RAID_HERO_TYPES_CACHE")
        ?? Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "data", "cache", "hero_types.json"));

    static void Dump(string dir, string file, object value) =>
        File.WriteAllText(Path.Combine(dir, file), JsonSerializer.Serialize(value, Json));
}
