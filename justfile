# raid-optimiser tasks. `just` lists them.
#
# This file is the one place that knows this machine's paths: `.env` (just configure) names the
# Proton prefix and the HH install, the rest are the game's own layout under them. Recipes pass
# them to the tools as arguments.

set positional-arguments
set dotenv-load

# The game's Proton prefix and the HH extractor inside it (override in .env: RAID_PREFIX, HH_DIR)
RAID_PREFIX := env("RAID_PREFIX", env("HOME") / ".local/share/Steam/steamapps/compatdata/2441943673/pfx")
HH_DIR := env("HH_DIR", RAID_PREFIX / "drive_c/hh")
appdata := RAID_PREFIX / "drive_c/users/steamuser/AppData"
# The game's install (bundles under it), its build (code, metadata) and its static-data cache
game_install := appdata / "Local/PlariumPlay/StandAloneApps/raid-shadow-legends"
game := game_install / "build"
metadata := game / "Raid_Data/il2cpp_data/Metadata/global-metadata.dat"
static_cache := appdata / "LocalLow/Plarium/Raid_ Shadow Legends/static-data"
web_port := env("WEB_PORT", "8000")
oracle_out := "/tmp/raider-oracle.json"
oracle_request_file := "/tmp/raider-oracle-request.txt"
# The roytu fork of Il2CppDumper (metadata v39+), built for net8.0
dumper := env("IL2CPP_DUMPER", env("HOME") / "repo/Il2CppDumper/Il2CppDumper/bin/Release/net8.0/Il2CppDumper.dll")
# Every Python source fmt, lint and style cover
py := "optimiser webui capture tools"

# List the recipes
default:
    @just --list --unsorted

# Only TLS to hellhades.com is intercepted; everything else is tunnelled untouched.
# ~/scripts/hh.sh finds the proxy by `mitmdump .*--listen-port 8080 .*hh_capture.py`: keep the order.
# The web UI's game commands (equip, preview, sell) through the HH extractor (extractor + game running)
proxy *args:
    uv run --group capture mitmdump --listen-host 127.0.0.1 --listen-port 8080 \
        --allow-hosts 'hellhades\.com(:\d+)?$' -s capture/hh_capture.py --flow-detail 0 "$@"

# Re-apply the HellHades sell/equip fix (after a HellHades update) in its install (-q: quiet)
hh-patch *args:
    uv run python -m tools.hh_patch "{{HH_DIR}}" "$@"

# Then checks the level multipliers base stats are computed from (optimiser/levels.py) are the game's.
# Re-export the game's static data after a game update (--full for the whole static.json)
static *args:
    mkdir -p data/game
    uv run python -m tools.static_export "{{static_cache}}" schema/schema.json data/game "$@"
    uv run python -m tools.check_levels metadata "{{metadata}}"

# Ask for this machine's paths (Raid's Proton prefix, the HH extractor) and save them in .env
configure:
    #!/usr/bin/env bash
    set -eu
    found=$(ls -d "$HOME"/.local/share/Steam/steamapps/compatdata/*/pfx 2>/dev/null \
        | while read -r p; do [ -d "$p/drive_c/users/steamuser/AppData/LocalLow/Plarium/Raid_ Shadow Legends" ] && echo "$p"; done \
        | head -1) || true
    default=${found:-{{RAID_PREFIX}}}
    read -rep "Raid's Proton prefix [$default]: " prefix
    prefix=${prefix:-$default}
    [ -d "$prefix/drive_c" ] || echo "warning: no drive_c under $prefix"
    roaming="$prefix/drive_c/users/steamuser/AppData/Roaming/HellHades Artifact Extractor"
    default=$prefix/drive_c/hh
    [ -d "$roaming" ] && default=$roaming
    read -rep "HH extractor install [$default]: " hh
    hh=${hh:-$default}
    [ -f "$hh/HellHades.ArtifactExtractor.Models.dll" ] || echo "warning: HH extractor not found at $hh (install it, then just update)"
    {
        echo "# Machine-specific paths, written by just configure (see .env.example)"
        echo "RAID_PREFIX=\"$prefix\""
        [ "$hh" = "$prefix/drive_c/hh" ] || echo "HH_DIR=\"$hh\""
    } > .env
    echo "saved .env"

# Create mitmproxy's CA (~/.mitmproxy) if missing and trust it in Raid's prefix (Wine stopped)
ca:
    #!/usr/bin/env bash
    set -eu
    cert=~/.mitmproxy/mitmproxy-ca-cert.pem
    if [ ! -f "$cert" ]; then
        uv run --group capture python -c \
            "from mitmproxy.certs import CertStore; CertStore.from_store('$HOME/.mitmproxy', 'mitmproxy', 2048)"
        echo "created $cert (keep ~/.mitmproxy private)"
    fi
    uv run python -m tools.wine_trust_ca "{{RAID_PREFIX}}" "$cert"

# Setup: paths (if no .env), mitmproxy's CA (Raid closed the first time only), then update
install:
    @[ -f .env ] || just configure
    just ca
    just update

# After a pull/game/HH update (Raid can run): deps, HH patch, game data, assets
update:
    uv sync --all-groups
    npm ci --silent
    @if [ -d "{{HH_DIR}}" ]; then just hh-patch -q; \
    else echo "HH extractor not found at {{HH_DIR}}: skipped the patch (just configure, then just update)"; fi
    just static
    just assets

# Build the memory reader (Rust, for the game's Wine prefix)
reader:
    cd reader && cargo build --release

# The reader's layout (offsets, enums), from the newest dump (just dump after a game update)
reader-layout:
    uv run python -m tools.reader_layout "$(ls -d data/dump/*/ | sort -V | tail -1)" data/cache/reader-layout.json

# Read the account out of the running game's memory (read-only) into data/captures/snapshot.json
read: reader
    @[ -f data/cache/reader-layout.json ] || just reader-layout
    plarium-umu "$PWD/reader/target/x86_64-pc-windows-gnu/release/raid-reader.exe" \
        "Z:$PWD/data/cache/reader-layout.json" "Z:$PWD/data/captures/snapshot.json"

# Start the web UI on http://127.0.0.1:<port> (WEB_PORT or 8000), auto-reloading (--no-reload)
web port=web_port *args:
    shift; uv run python -m webui --port "{{port}}" "$@"

# Stop the web UI (by port)
web-stop port=web_port:
    -fuser -k "{{port}}/tcp"

# Restart the web UI (it reloads on Python changes by itself)
web-restart port=web_port: (web-stop port)
    just web "{{port}}"

# Extract portraits, set icons and piece art from the game's Unity bundles
assets:
    uv run --group assets python -m tools.extract_assets "{{game_install}}"

# Format with black
fmt:
    uv run --group dev black {{py}}

# Lint with ruff
lint:
    uv run --group dev ruff check {{py}}

# House style checker
style:
    uv run --project ~/repo/python-style python-style {{py}}

# The web UI's CSS: Prettier's format (one declaration a line), then stylelint (standard
# config, properties in one order, nesting at most 3 deep)
css:
    node_modules/.bin/prettier --check --log-level warn "webui/static/*.css"
    node_modules/.bin/stylelint "webui/static/*.css"

# Fix what can be: format, sort properties, format again
css-fix:
    node_modules/.bin/prettier --write --log-level warn "webui/static/*.css"
    node_modules/.bin/stylelint --fix "webui/static/*.css"
    node_modules/.bin/prettier --write --log-level warn "webui/static/*.css"

# Format, lint and style-check
check: fmt lint style css

# Dump the installed game's IL2CPP metadata (offline) into data/dump/<game version>
dump:
    #!/usr/bin/env bash
    set -eu
    version=$(ls "{{static_cache}}" | sort -V | tail -1)
    out=data/dump/$version
    mkdir -p "$out"
    dotnet "{{dumper}}" "{{game}}/GameAssembly.dll" "{{metadata}}" "$out"
    echo "dumped $version -> $out"

# Regenerate schema/schema.json from an IL2CPP dump (default: the newest in data/dump)
schema dump_cs="":
    #!/usr/bin/env bash
    set -eu
    dump_cs="{{dump_cs}}"
    [ -n "$dump_cs" ] || dump_cs=$(ls -d data/dump/*/ | sort -V | tail -1)dump.cs
    uv run python -m tools.gen_schema "$dump_cs" schema/schema.json

# After a game update changes the data's shape: re-dump the game, regenerate the schema, re-export
schema-refresh: dump schema static

# Compare the computed base stats (optimiser/levels.py) with a raider oracle table
check-levels oracle="data/game/base_stats_6_60.json":
    uv run python -m tools.check_levels oracle "{{oracle}}" data/game/hero_types.json

# Write the raider oracle's request file (inject into ~/tmp/inject-test only!)
oracle-request out=oracle_request_file:
    uv run python -m tools.oracle_request data/game/hero_types.json "{{out}}"

# Import the raider oracle's output into data/game/{base_stats_6_60,level_curve}.json
oracle-import input=oracle_out:
    uv run python -m tools.oracle_import "{{input}}" data/game/hero_types.json data/game/

# Champions (each mythical form apart) that may need a scaling exception (--all, --name X)
exceptions *args:
    uv run python -m optimiser.accessories.scaling_report "$@"

# The enemy store: areas, an area's or a stage's enemies and restrictions, the Chimera's trials
# (just enemies area CooperationEventWorldBoss; stage 13019006 --skills; chimera --difficulty Hard)
enemies *args:
    uv run python -m optimiser.enemy_report "$@"
