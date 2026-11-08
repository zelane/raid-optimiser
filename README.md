# raid-export

Tees the HellHades Artifact Extractor's account upload (`POST /api/Account/v2`)
through mitmproxy and decodes it to JSON with HH's own `Models.dll`.

```
capture/hh_capture.py   mitmproxy addon: saves upload -> captures/<ts>.bin, runs decoder
decoder/                C# decoder (references DLLs in the HH install dir)
run-proxy.sh            starts mitmdump on 127.0.0.1:8080, MITMs only *.hellhades.com
captures/latest/        newest export: champions.json, artifacts.json, hero-types.json, account.json
```

## One-time setup

1. `./run-proxy.sh` once. It builds the decoder and creates `~/.mitmproxy/` with the CA.
2. Trust the CA so Wine/Proton accepts it (Wine's crypt32 picks up host roots):
   `sudo trust anchor ~/.mitmproxy/mitmproxy-ca-cert.pem`
   This trusts it system-wide. Undo with `sudo trust anchor --remove ~/.mitmproxy/mitmproxy-ca-cert.pem`.
   Keep `~/.mitmproxy/` private while it's trusted.
3. Steam → extractor shortcut → Properties → Launch options:
   `HTTPS_PROXY=http://127.0.0.1:8080 HTTP_PROXY=http://127.0.0.1:8080 %command%`

## Use

Run `./run-proxy.sh`, then start the extractor and game. Each account sync writes a new
`captures/<timestamp>/`. Re-decode a capture manually:
`bin/raid-export captures/<ts>.bin out/`

After an extractor update, rebuild so the decoder picks up the new models:
`dotnet build decoder -c Release -o bin`. Use `-p:HHDir=...` or `HH_DIR=...` if the install moves.

## Game static data (sets, hero types)

`./update-static.sh` decodes the game's own cache
(`AppData/LocalLow/Plarium/Raid_ Shadow Legends/static-data/<version>/<hash>`, MessagePack +
Lz4BlockArray) and writes:

- `static/sets.json` – every artifact set: pieces, per-tier stat bonuses (variable sets such as
  Stone Skin list the cumulative bonus at each piece count), names/descriptions
- `static/hero_types.json` – names, faction, rarity, and per-form element/role/unscaled base stats

Key names and types come from `schema/schema.json`, generated from an IL2CPP dump:
`python3 -I tools/gen_schema.py ~/repo/raider/dump/dump.cs schema/schema.json`.
The export validates itself (e.g. set bonuses must match the in-game description text) and
exits non-zero if the schema no longer fits; notes about unknown keys elsewhere are harmless.

## Scaled base stats (raider oracle, throwaway account only)

Static data holds unscaled stats; the rank/level scaling lives in game code. `~/repo/raider`'s
payload calls the game's own `GetBaseStats` on temporary in-memory heroes (never added to the
account) for each line of `/tmp/raider-oracle-request.txt`:

```
python3 -I tools/oracle_request.py static/hero_types.json /tmp/raider-oracle-request.txt
(cd ~/repo/raider && ./run.sh)          # game running + logged in in ~/tmp/inject-test
python3 -I tools/oracle_import.py /tmp/raider-oracle.json static/hero_types.json static/
```

- `static/base_stats_6_60.json`: exact base stats at 6* L60 for every type/form
- `static/level_curve.json`: ATK/DEF multiplier per grade/level (HP = static × 15 × m);
  shared by all types to within rounding. SPD/RES/ACC/crit don't scale (crit is % in static data).

An optional 5th request column sets the empower level and adds the game's `CalcEmpowerBonus`.

## Non-gear bonuses

`./update-static.sh` also writes `static/bonuses.json` from the game data. Percentages apply
to base stats:

- `great_hall[stat][level-1]`: bonus per level (max: +20% HP/ATK/DEF, +25% C.DMG, +80 ACC/RES);
  the optimiser uses the account's levels per affinity from the capture (complete if absent)
- `arena[league]`: classic arena league bonus, % of base HP/ATK/DEF (Gold V +22%)
- `empower[rarity][level-1]`: cumulative; verified against the game's `CalcEmpowerBonus`
- `awakening[rarity][AwakenedGrade-1]`: cumulative flat bonuses.
  Ascension (0-6) is the last digit of `TypeId`; each ascended type has its own base
  stats, already covered by `base_stats_6_60.json`.
- `masteries[id]`: the 13 stat masteries; Lore of Steel is `set_bonus_multiplier: 1.15`
  (applied to artifact set stat bonuses). Per-champion mastery ids, `AwakenedGrade` and
  `EmpowerLevel` come from `captures/latest/champions.json`.

## Gear optimiser

```
uv run python -m optimiser "Anaxia the Reborn" --set Lethal=4 --set "Stone Skin=4" \
    --min SPD=200 --min ACC=150 --rank HP,DEF,SPD --builds 3 [--pool free] [--slack 0.01]
```

A HiGHS MILP over the latest capture: one binary per wearable artifact (accessories by
faction), exact set bonuses through piece-count variables, then each `--rank` stat maximised
in turn, held within `--slack` of its best before the next. Further builds exclude earlier
ones exactly. C.RATE/C.DMG limits are in %; ranking C.RATE stops at 100 %. `current` is the
champion's gear under the same model: compare it with the game to check the model.
`--pool all` (default) includes gear worn by others and says who wears it.

Damage: `--rank DMG,... --skill "Song of Steel" --enemy-def 6000` (or the Damage row in the
web form) ranks a skill's crit-hit damage, as the game's `DamageCalculator` computes it (read
from the game code): formula × (1 + books) × (1 + C.DMG) × [1 - 0.85 (1 - e^(-effDEF/1500))],
effDEF = DEF × (1 - ignore DEF), skill and set ignore DEF adding. Ranked by its log, so the
model stays a MILP. Skills whose formula uses more than the champion's own stats (target HP,
battle state) can't be ranked. Pair it with `--min CR=100`. Leaves out buffs/debuffs,
affinity and the dealt-damage substats.

Includes the account's classic arena league bonus (from the capture; Gold V if missing).
Includes the stats of the relics each champion wears (stones add skills only).
Not modelled: blessings, faction-guardian bonuses.

## Web UI

`uv run python -m webui`, then http://127.0.0.1:8000: search a champion, set targets, view
builds with every piece's full detail (slot, set, rank, rarity, level, main stat, substats with
glyphs and rolls, ascension, faction lock, who wears it now, artifact id). The account reloads
whenever the proxy writes a new capture.

Layers: `optimiser/` (model and solver) <- `webui/service.py` (framework-free view models,
ready to serve as JSON for a Vue front end) <- `webui/forms.py` (form -> `Request`) <-
`webui/app.py` + `templates/` (FastAPI, Jinja, htmx, Pico CSS). Icons and portraits come
from the game's own Unity bundles: `uv run --group assets python -I tools/extract_assets.py`
writes `webui/static/assets/{portraits,sets,pieces}/` (newest bundle version wins; rerun after
a game update). Anything missing falls back to text.

## If TLS fails (extractor log shows SSL / certificate errors)

- Proton's pressure-vessel container may not see the host CA store. Options:
  import the CA into the prefix's registry Root store instead, or
- fall back to `--local` mode (the extractor talks plain HTTP to `localhost:5000`; needs a
  stub login server and HellHades stops getting the data).
