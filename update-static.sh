#!/bin/sh
# Re-export the game's cached static data into static/sets.json + static/hero_types.json.
# Run after a game update. Pass --full to also write the whole named static.json (~100MB).
# If validation fails, the dump is stale: re-dump the game, then
#   python3 -I tools/gen_schema.py <dump.cs> schema/schema.json
cd "$(dirname "$0")" || exit 1
[ -x bin/raid-export ] || dotnet build decoder -c Release -o bin || exit 1
bin/raid-export static static/static-raw.json || exit 1
exec python3 -I tools/static_export.py static/static-raw.json schema/schema.json static "$@"
