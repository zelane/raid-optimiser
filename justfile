# raid-optimiser tasks. `just` lists them.

set positional-arguments
set dotenv-load

oracle_out := "/tmp/raider-oracle.json"
oracle_request_file := "/tmp/raider-oracle-request.txt"
# The game's Proton prefix and the HH extractor inside it (override: RAID_PREFIX, HH_DIR)
prefix := env("RAID_PREFIX", env("HOME") / ".local/share/Steam/steamapps/compatdata/2441943673/pfx")
hh_dir := env("HH_DIR", prefix / "drive_c/hh")
web_port := env("WEB_PORT", "8000")
game := prefix / "drive_c/users/steamuser/AppData/Local/PlariumPlay/StandAloneApps/raid-shadow-legends/build"
# The roytu fork of Il2CppDumper (metadata v39+), built for net8.0
dumper := env("IL2CPP_DUMPER", env("HOME") / "repo/Il2CppDumper/Il2CppDumper/bin/Release/net8.0/Il2CppDumper.dll")

# List the recipes
default:
    @just --list --unsorted

# Capture: mitmproxy tees the HH extractor's upload (extractor + game running)
proxy *args:
    ./run-proxy.sh "$@"

# Re-export the game's static data after a game update (--full for the whole static.json)
static *args:
    ./update-static.sh "$@"

# Ask for this machine's paths (Raid's Proton prefix, the HH extractor) and save them in .env
configure:
    #!/usr/bin/env bash
    set -eu
    found=$(ls -d "$HOME"/.local/share/Steam/steamapps/compatdata/*/pfx 2>/dev/null \
        | while read -r p; do [ -d "$p/drive_c/users/steamuser/AppData/LocalLow/Plarium/Raid_ Shadow Legends" ] && echo "$p"; done \
        | head -1) || true
    default=${RAID_PREFIX:-${found:-{{prefix}}}}
    read -rep "Raid's Proton prefix [$default]: " prefix
    prefix=${prefix:-$default}
    [ -d "$prefix/drive_c" ] || echo "warning: no drive_c under $prefix"
    roaming="$prefix/drive_c/users/steamuser/AppData/Roaming/HellHades Artifact Extractor"
    default=$prefix/drive_c/hh
    [ -d "$roaming" ] && default=$roaming
    default=${HH_DIR:-$default}
    read -rep "HH extractor install [$default]: " hh
    hh=${hh:-$default}
    [ -f "$hh/HellHades.ArtifactExtractor.Models.dll" ] || echo "warning: HH extractor not found at $hh (install it, then just decoder)"
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
        uvx --from mitmproxy python -c \
            "from mitmproxy.certs import CertStore; CertStore.from_store('$HOME/.mitmproxy', 'mitmproxy', 2048)"
        echo "created $cert (keep ~/.mitmproxy private)"
    fi
    python3 -I tools/wine_trust_ca.py "{{prefix}}" "$cert"

# First-time setup: paths (if there's no .env yet), mitmproxy's CA, Python deps, the decoder
install:
    @[ -f .env ] || just configure
    just ca
    uv sync --all-groups
    @hh=$(just --evaluate hh_dir); if [ -d "$hh" ]; then just decoder; \
    else echo "HH extractor not found at $hh: skipped the decoder (just configure, then just decoder)"; fi

# (Re)build the C# decoder into bin/
decoder:
    dotnet build decoder -c Release -o bin -p:HHDir="{{hh_dir}}"

# Start the web UI on http://127.0.0.1:<port> (default WEB_PORT or 8000), reloading on Python
# changes (--no-reload: off)
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
    uv run --group assets python -I tools/extract_assets.py

# Format with black
fmt:
    uv run --group dev black optimiser webui

# Lint with ruff
lint:
    uv run --group dev ruff check optimiser webui

# House style checker
style:
    uv run --project ~/repo/python-style python-style optimiser webui

# Format, lint and style-check
check: fmt lint style

# Dump the installed game's IL2CPP metadata (offline) into data/dump/<game version>
dump:
    #!/usr/bin/env bash
    set -eu
    version=$(ls "{{prefix}}/drive_c/users/steamuser/AppData/LocalLow/Plarium/Raid_ Shadow Legends/static-data" | sort -V | tail -1)
    out=data/dump/$version
    mkdir -p "$out"
    dotnet "{{dumper}}" "{{game}}/GameAssembly.dll" "{{game}}/Raid_Data/il2cpp_data/Metadata/global-metadata.dat" "$out"
    echo "dumped $version -> $out"

# Regenerate schema/schema.json from an IL2CPP dump (default: the newest in data/dump)
schema dump_cs="":
    #!/usr/bin/env bash
    set -eu
    dump_cs="{{dump_cs}}"
    [ -n "$dump_cs" ] || dump_cs=$(ls -d data/dump/*/ | sort -V | tail -1)dump.cs
    python3 -I tools/gen_schema.py "$dump_cs" schema/schema.json

# Compare the computed base stats (optimiser/levels.py) with a raider oracle table
check-levels oracle="data/game/base_stats_6_60.json":
    uv run python -I tools/check_levels.py oracle "{{oracle}}" data/game/hero_types.json

# Write the raider oracle's request file (inject into ~/tmp/inject-test only!)
oracle-request out=oracle_request_file:
    python3 -I tools/oracle_request.py data/game/hero_types.json "{{out}}"

# Import the raider oracle's output into data/game/{base_stats_6_60,level_curve}.json
oracle-import input=oracle_out:
    python3 -I tools/oracle_import.py "{{input}}" data/game/hero_types.json data/game/

# Champions (each mythical form apart) that may need a scaling exception (--all, --name X)
exceptions *args:
    uv run python -m optimiser.accessories.scaling_report "$@"

# The enemy store: areas, an area's or a stage's enemies and restrictions, the Chimera's trials
# (just enemies area CooperationEventWorldBoss; stage 13019006 --skills; chimera --difficulty Hard)
enemies *args:
    uv run python -m optimiser.enemy_report "$@"
