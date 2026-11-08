using HellHades.ArtifactExtractor.Models;
using Newtonsoft.Json;

// The account upload doesn't include hero types (the extractor only fetches them
// for its "add all heroes" debug mode), so get them from the same public endpoint
// the extractor uses, deserialized the same way (Newtonsoft -> HH's HeroType).
static class HeroTypes
{
    const string Url = "https://raidoptimiser.hellhades.com/api/StaticData/hero_types";
    static readonly TimeSpan MaxAge = TimeSpan.FromDays(1);

    public static Dictionary<int, HeroType> Load(string cachePath, IEnumerable<int> neededIds)
    {
        var cached = File.Exists(cachePath) ? Parse(File.ReadAllText(cachePath)) : null;
        var age = cached != null ? DateTime.UtcNow - File.GetLastWriteTimeUtc(cachePath) : TimeSpan.MaxValue;
        var complete = cached != null && neededIds.All(cached.ContainsKey);
        // Refetch daily, or sooner (at most hourly) when a new champion's type is missing.
        if (age < MaxAge && (complete || age < TimeSpan.FromHours(1)))
            return cached!;

        try
        {
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(60) };
            http.DefaultRequestHeaders.Accept.ParseAdd("application/json");
            var json = http.GetStringAsync(Url).GetAwaiter().GetResult();
            var parsed = Parse(json);
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(cachePath))!);
            File.WriteAllText(cachePath + ".tmp", json);
            File.Move(cachePath + ".tmp", cachePath, overwrite: true);
            Console.WriteLine($"hero types: fetched {parsed.Count} from server");
            return parsed;
        }
        catch (Exception e) when (cached != null)
        {
            // Offline / server error: a stale list is better than no names.
            Console.Error.WriteLine($"hero types: refresh failed ({e.Message}); using cached list");
            if (!complete) File.SetLastWriteTimeUtc(cachePath, DateTime.UtcNow - MaxAge); // retry next run
            return cached;
        }
    }

    static Dictionary<int, HeroType> Parse(string json) =>
        (JsonConvert.DeserializeObject<HeroType[]>(json) ?? [])
            .GroupBy(t => t.Id).ToDictionary(g => g.Key, g => g.First());
}
