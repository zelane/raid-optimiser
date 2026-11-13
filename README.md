# raid-optimiser

A gear optimiser for Raid: Shadow Legends. The account is read out of the running game's
memory (read-only, from outside the process); builds go back to the game through the
HellHades Artifact Extractor, whose hub connection the proxy injects commands into.

```
reader/                 Rust memory reader, run in the game's prefix (just read)
capture/hh_capture.py   mitmproxy addon: equip / preview / sell through the extractor
optimiser/              the model and solver
webui/                  the web UI
tools/                  the game-data, layout, asset, schema, CA and HH-patch tools (python -m tools.<name>)
justfile                every task (`just` lists them); the only place with machine paths
data/                   everything that isn't code (gitignored):
  captures/snapshot.json  the account (just read)
  game/                 the game's tables (just static)
  dump/<version>/       IL2CPP dump of the installed game (just dump)
  state/                the optimiser's store (locks, assumptions, runs)
  cache/                the reader's layout (just reader-layout), accessory scores
```

## One-time setup

1. `just install`, with the game and the extractor closed: asks for paths (into `.env`, or
   `just configure` later), creates mitmproxy's CA in `~/.mitmproxy/` and adds it to the
   prefix's user root store (`just ca`, `tools/wine_trust_ca.py`; only adding it needs Wine
   stopped), then runs `just update`. Trusting it on the host (`trust anchor`) isn't
   enough under umu: Proton runs in the Steam Linux Runtime, whose Wine syncs its machine root
   store from the runtime's certificates. Keep `~/.mitmproxy/` private while it's trusted.
2. Steam → extractor shortcut → Properties → Launch options:
   `HTTPS_PROXY=http://127.0.0.1:8080 HTTP_PROXY=http://127.0.0.1:8080 %command%`

## Use

With the game running and logged in, `just read` writes the account to
`data/captures/snapshot.json` (about 2.5 s); the web UI picks it up. For the equip, preview and
sell buttons, run `just proxy`, then start the extractor.

After a pull, a game update or an extractor update, run `just update` (Raid can stay open): it
syncs Python deps, re-applies the HH patch, re-exports the game data and
re-extracts the assets. After a game update also run `just dump` and `just reader-layout`, so
the reader finds the game's fields. Restart the extractor afterwards if the patch changed. Set
`HH_DIR` in `.env` if the extractor install moves.

## Game static data (sets, hero types)

`just static` decodes the game's own cache
(`AppData/LocalLow/Plarium/Raid_ Shadow Legends/static-data/<version>/<hash>`, MessagePack +
Lz4BlockArray, `tools/static_decode.py`) and writes:

- `data/game/sets.json` – every artifact set: pieces, per-tier stat bonuses (variable sets such as
  Stone Skin list the cumulative bonus at each piece count), names/descriptions
- `data/game/hero_types.json` – names, faction, rarity, and per-form element/role/unscaled base stats

Key names and types come from `schema/schema.json`, generated from an IL2CPP dump:
`just dump` (Il2CppDumper over the installed game, offline), then `just schema`;
`just schema-refresh` does both and re-exports. Run it when the export says the dump predates
the game version.
The export validates itself (e.g. set bonuses must match the in-game description text) and
exits non-zero if the schema no longer fits; notes about unknown keys elsewhere are harmless.

## Scaled base stats

Static data holds unscaled stats; the rank/level scaling lives in game code
(`BattleStats.CalcValue`), which `optimiser/levels.py` reproduces from its disassembly,
with the game's multiplier table. `just static` checks the table is still in the game's
metadata (`tools/check_levels.py`); if a game update changes it, re-dump and read it again.

### Checking against the game (raider oracle, throwaway account only)

`~/repo/raider`'s payload calls the game's own `GetBaseStats` on temporary in-memory heroes
(never added to the account) for each line of `/tmp/raider-oracle-request.txt`:

```
just oracle-request
(cd ~/repo/raider && ./run.sh)          # game running + logged in in ~/tmp/inject-test
just oracle-import
```

- `data/game/base_stats_6_60.json`: exact base stats at 6* L60 for every type/form;
  `just check-levels` compares the formula with it
- `data/game/level_curve.json`: ATK/DEF multiplier per grade/level (no longer used)

An optional 5th request column sets the empower level and adds the game's `CalcEmpowerBonus`.

## Non-gear bonuses

`just static` also writes `data/game/bonuses.json` from the game data. Percentages apply
to base stats:

- `great_hall[stat][level-1]`: bonus per level (max: +20% HP/ATK/DEF, +25% C.DMG, +80 ACC/RES);
  the optimiser uses the account's levels per affinity (complete if absent)
- `arena[league]`: classic arena league bonus, % of base HP/ATK/DEF (Gold V +22%)
- `empower[rarity][level-1]`: cumulative; verified against the game's `CalcEmpowerBonus`
- `awakening[rarity][AwakenedGrade-1]`: cumulative flat bonuses.
  Ascension (0-6) is the last digit of `TypeId`; each ascended type has its own base
  stats (`hero_types.json`).
- `masteries[id]`: the 13 stat masteries; Lore of Steel is `set_bonus_multiplier: 1.15`
  (applied to artifact set stat bonuses). Per-champion mastery ids, awakening and empower
  levels come from the snapshot.

## Gear optimiser

Run from the web UI's champion page (below). A HiGHS MILP over the account: one
binary per wearable artifact (accessories by faction), exact set bonuses through piece-count
variables, then each ranked stat maximised in turn by priority, held within the slack of its
best before the next. Further builds exclude earlier ones exactly. C.RATE/C.DMG limits are in
%; ranking C.RATE stops at 100 %. `current` is the champion's gear under the same model:
compare it with the game to check the model. The gear pool "Any" includes gear worn by
others and says who wears it.

Damage: the Damage row of the form ranks a skill's crit-hit damage against an enemy DEF, as
the game's `DamageCalculator` computes it (read from the game code): formula × (1 + books) ×
(1 + C.DMG) × [1 - 0.85 (1 - e^(-effDEF/1500))], effDEF = DEF × (1 - ignore DEF), skill and
set ignore DEF adding. Ranked by its log, so the model stays a MILP. Skills whose formula uses
more than the champion's own stats (target HP, battle state) can't be ranked. Pair it with a
C.RATE minimum of 100. Leaves out buffs/debuffs, affinity and the dealt-damage substats.

Includes the account's classic arena league bonus (Gold V if the game doesn't say).
Includes the stats of the relics each champion wears (stones add skills only).
Not modelled: blessings, faction-guardian bonuses.

## Web UI

`just web`, then http://127.0.0.1:8000: search a champion, set targets, view
builds with every piece's full detail (slot, set, rank, rarity, level, main stat, substats with
glyphs and rolls, ascension, faction lock, who wears it now, artifact id). The account reloads
whenever `just read` writes a new snapshot.

Layers: `optimiser/` (model and solver) <- `webui/service/` (framework-free view models, a
module per page, ready to serve as JSON for a Vue front end) <- `webui/forms.py` (form -> `Request`) <-
`webui/app.py` + `templates/` (FastAPI, Jinja, htmx, Pico CSS). Icons and portraits come
from the game's own Unity bundles: `just assets` (`tools/extract_assets.py`)
writes `webui/static/assets/{portraits,sets,pieces}/` (newest bundle version wins; rerun after
a game update). Anything missing falls back to text.

## If TLS fails (extractor log shows SSL / certificate errors)

- Proton's pressure-vessel container may not see the host CA store. Options:
  import the CA into the prefix's registry Root store instead, or
- fall back to `--local` mode (the extractor talks plain HTTP to `localhost:5000`; needs a
  stub login server and HellHades stops getting the data).
