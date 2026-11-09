#!/bin/sh
# Re-export the game's cached static data into data/game/{sets,hero_types,bonuses,skills,glyphs,gear}.json
# and check the level multipliers base stats are computed from are still the game's.
# Run after a game update. Pass --full to also write the whole named static.json (~100MB).
# If validation fails, the dump is stale: re-dump the game, then
#   python3 -I tools/gen_schema.py <dump.cs> schema/schema.json
cd "$(dirname "$0")" || exit 1
[ -x bin/raid-export ] || dotnet build decoder -c Release -o bin || exit 1
mkdir -p data/game || exit 1
bin/raid-export static data/game/static-raw.json || exit 1
python3 -I tools/static_export.py data/game/static-raw.json schema/schema.json data/game "$@" || exit 1
# Base stats by level are computed (optimiser/levels.py) from a table in the game's metadata.
metadata="${RAID_PREFIX:?set RAID_PREFIX (just static reads .env)}/drive_c/users/steamuser/AppData/Local/PlariumPlay/StandAloneApps/raid-shadow-legends/build/Raid_Data/il2cpp_data/Metadata/global-metadata.dat"
exec uv run python -I tools/check_levels.py metadata "$metadata"
