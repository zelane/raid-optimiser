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
# The Proton the game runs under (override in .env: RAID_PROTON); `just read` runs the reader
# with it inside the game's own umu container, unless a `plarium-umu` wrapper is on the PATH
RAID_PROTON := env("RAID_PROTON", env("HOME") / ".local/share/Steam/compatibilitytools.d/GE-Proton11-11-x86_64")
appdata := RAID_PREFIX / "drive_c/users/steamuser/AppData"
# The game's install (bundles under it), its build (code, metadata) and its static-data cache
game_install := appdata / "Local/PlariumPlay/StandAloneApps/raid-shadow-legends"
game := game_install / "build"
metadata := game / "Raid_Data/il2cpp_data/Metadata/global-metadata.dat"
static_cache := appdata / "LocalLow/Plarium/Raid_ Shadow Legends/static-data"
web_port := env("WEB_PORT", "8000")
oracle_out := "/tmp/raider-oracle.json"
oracle_request_file := "/tmp/raider-oracle-request.txt"
# The roytu fork of Il2CppDumper (metadata v39+): its checkout (override in .env:
# IL2CPP_DUMPER_DIR; just install clones and builds it there) and its net8.0 build
dumper_dir := env("IL2CPP_DUMPER_DIR", env("HOME") / "repo/Il2CppDumper")
dumper := dumper_dir / "Il2CppDumper/bin/Release/net8.0/Il2CppDumper.dll"
# Every Python source fmt, lint and style cover
py := "optimiser webui capture tools"

# List the recipes
default:
    @just --list --unsorted

# Only TLS to hellhades.com is intercepted; everything else is tunnelled untouched.
# ~/scripts/hh.sh finds the proxy and its port by `mitmdump .*--listen-port <port> .*hh_capture.py`: keep the order.
# The web UI's game commands (equip, preview, sell) through the HH extractor (extractor + game running)
proxy *args:
    uv run --group capture mitmdump --listen-host 127.0.0.1 --listen-port 8089 \
        --allow-hosts 'hellhades\.com(:\d+)?$' -s capture/hh_capture.py --flow-detail 0 "$@"

# Re-apply the HellHades sell/equip fix (after a HellHades update) in its install (-q: quiet)
[private]
hh-patch *args:
    uv run python -m tools.hh_patch "{{HH_DIR}}" "$@"

# Export the game's tables from its static-data cache (--full for the whole static.json), then
# check the level multipliers base stats are computed from (optimiser/levels.py) are the game's.
# The game writes that cache when it runs, so after an update it lags until the game is launched.
[private]
static *args:
    #!/usr/bin/env bash
    set -eu
    mkdir -p data/game
    uv run python -m tools.static_export "{{static_cache}}" schema/schema.json data/game "$@"
    uv run python -m tools.check_levels metadata "{{metadata}}"
    data=$(ls "{{static_cache}}" | sort -V | tail -1)
    code=$(basename "$(ls -d data/dump/*/ | sort -V | tail -1)")
    if [ "$data" != "$code" ]; then
        echo "note: the game's static data is $data, its code $code: launch the game once, then just update" >&2
    fi

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
[private]
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

# A fresh checkout: paths (if no .env), the tools (Il2CppDumper, the reader's Rust target),
# mitmproxy's CA (Raid closed the first time only), then update
[doc("Set up a fresh checkout (Raid closed the first time), then update")]
install:
    @[ -f .env ] || just configure
    just tools
    just ca
    just update

# After a pull, a game update or an HH update (Raid can run; launch it once after a game
# update first, so it writes its static data): deps, the HH patch, the game's dump (when its
# code changed), the reader's layout and build, the schema and tables, assets, the front end
[doc("After a pull, a game update (launch the game once first) or an HH update")]
update:
    uv sync --all-groups
    npm ci --silent
    @if [ -d "{{HH_DIR}}" ]; then just hh-patch -q; \
    else echo "HH extractor not found at {{HH_DIR}}: skipped the patch (just configure, then just update)"; fi
    just dump
    just reader-layout
    just reader
    just schema
    just static
    just assets
    just frontend-build

# What install needs besides the project's own deps: Il2CppDumper (cloned and built if
# missing) and the reader's Rust target; the target's linker (mingw-w64) is checked only
[private]
tools:
    #!/usr/bin/env bash
    set -eu
    if [ ! -f "{{dumper}}" ]; then
        [ -d "{{dumper_dir}}" ] || git clone https://github.com/roytu/Il2CppDumper "{{dumper_dir}}"
        dotnet build "{{dumper_dir}}/Il2CppDumper/Il2CppDumper.csproj" -c Release -f net8.0 \
            -p:RollForward=Major
    fi
    sed -i 's/"RequireAnyKey": true/"RequireAnyKey": false/' "$(dirname "{{dumper}}")/config.json"
    rustup target add x86_64-pc-windows-gnu
    command -v x86_64-w64-mingw32-gcc >/dev/null \
        || echo "warning: no x86_64-w64-mingw32-gcc: install mingw-w64-gcc to build the reader" >&2

# Build the memory reader (Rust, for the game's Wine prefix)
[private]
reader:
    cd reader && cargo build --release

# The reader's layout (offsets, enums), from the newest dump
[private]
reader-layout:
    uv run python -m tools.reader_layout "$(ls -d data/dump/*/ | sort -V | tail -1)" data/cache/reader-layout.json

# The events (data/captures/events.json) are apart from the account: they change far more often.
# Read the account and its events out of the running game's memory (read-only) into data/captures
read: reader
    just reader-run

# The events every 5 s, the rest once the account has changed and settled for 20 s, each file
# rewritten only when it changes; waits for the game when it isn't running (reader/src/watch.rs).
# Keep reading the account while the game runs (read-only), as read does, when it changes
watch: reader
    #!/usr/bin/env bash
    # The reader runs on in the game's container when its launcher is stopped: stop it too
    trap 'pkill -f "raid-reader[.]exe --watch" || true' EXIT INT TERM
    just reader-run --watch

# The reader, in the running game's prefix, with the layout and the files it writes
[private]
reader-run *flags:
    just reader-exec {{flags}} "Z:$PWD/data/cache/reader-layout.json" \
        "Z:$PWD/data/captures/snapshot.json" "Z:$PWD/data/captures/events.json"

# The finished fights the game still holds in memory (the last one's, kept for its result
# screen; background runs'), each written to data/captures/results/<setup id>.json, read only:
# `just check-capture` replays a captured fight and compares
results: reader
    mkdir -p data/captures/results
    just reader-exec --results "Z:$PWD/data/cache/reader-layout.json" "Z:$PWD/data/captures/results"

# A captured fight replayed on its own seed and compared with what the game recorded for it
# (`just results` after the fight): outcome, turns, each champion's result-screen rows
check-capture setup:
    #!/usr/bin/env bash
    set -eu
    id=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["z"])' "{{setup}}")
    recorded="data/captures/results/$id.json"
    [ -f "$recorded" ] || { echo "no recorded result for $id: just results, after the fight" >&2; exit 1; }
    rm -rf data/cache/host/results && mkdir -p data/cache/host/results
    just host-run fight "{{setup}}" 1 data/cache/host/results
    uv run python -m optimiser.fights data/cache/host/results --against "$recorded"

# The reader exe with these arguments, run in the running game's prefix
[private]
reader-exec *args:
    #!/usr/bin/env bash
    set -euo pipefail
    [ -f data/cache/reader-layout.json ] || just reader-layout
    exe="$PWD/reader/target/x86_64-pc-windows-gnu/release/raid-reader.exe"
    if command -v plarium-umu >/dev/null; then exec plarium-umu "$exe" "$@"; fi
    # Inside the running game's umu container, sharing its wineserver (as ~/scripts/hh.sh
    # does): umu names the container's service after the md5 of the resolved prefix path.
    client="$HOME/.local/share/umu/steamrt4/pressure-vessel/bin/steam-runtime-launch-client"
    bus="com.steampowered.App$(printf %s "$(readlink -f "{{RAID_PREFIX}}")" | md5sum | cut -d' ' -f1)"
    if ! "$client" --list 2>/dev/null | grep -qxF -- "--bus-name=$bus"; then
        echo "Raid isn't running in {{RAID_PREFIX}} (no umu container for it)" >&2
        exit 1
    fi
    exec "$client" --bus-name="$bus" --directory="$PWD" -- \
        "{{RAID_PROTON}}/proton" runinprefix "$exe" "$@"

# Start the web UI on http://127.0.0.1:<port> (WEB_PORT or 8000), auto-reloading (--no-reload)
web port=web_port *args:
    shift; uv run python -m webui --port "{{port}}" "$@"

# The web UI with the front end's dev server (hot reload of Vue pages): both stop together
web-dev port=web_port:
    #!/usr/bin/env bash
    set -eu
    trap 'kill 0' EXIT
    just frontend-types
    npm run --silent dev &
    VITE_DEV=http://127.0.0.1:5173 uv run python -m webui --port "{{port}}"

# The Vue pages' prop types, from webui/service's dataclasses
frontend-types:
    uv run python -m tools.gen_ts_types webui/frontend/src/types/generated

# Build the front end into webui/static/dist (the web UI serves it)
frontend-build: frontend-types
    npm run --silent build

# The front end: Prettier's format, and the Vue pages type-checked against the prop types
frontend-check: frontend-types
    node_modules/.bin/prettier --check --log-level warn "webui/frontend/**/*.{ts,vue}"
    npm run --silent typecheck

# The accessory seeds (champion types, set fits): seed what isn't, and list them; --reset backs
# the store up and seeds both again, losing the Weights tab's changes
seed *args:
    uv run python -m tools.seed "$@"

# Stop the web UI (by port)
web-stop port=web_port:
    -fuser -k "{{port}}/tcp"

# Restart the web UI (it reloads on Python changes by itself)
web-restart port=web_port: (web-stop port)
    just web "{{port}}"

# Extract portraits, set icons and piece art from the game's Unity bundles
[private]
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
    node_modules/.bin/stylelint "webui/static/*.css" "webui/frontend/src/**/*.vue"

# Fix what can be: format, sort properties, format again
css-fix:
    node_modules/.bin/prettier --write --log-level warn "webui/static/*.css"
    node_modules/.bin/stylelint --fix "webui/static/*.css" "webui/frontend/src/**/*.vue"
    node_modules/.bin/prettier --write --log-level warn "webui/static/*.css"

# Format, lint and style-check
check: fmt lint style css frontend-check

# Dump the installed game's IL2CPP metadata (offline) into data/dump/<game version>, unless a
# dump of this code exists (source.sha256: its GameAssembly.dll and metadata). The version is
# the code's own (StableManifestVersion), not the static data's, which lags until the game runs.
[private]
dump:
    #!/usr/bin/env bash
    set -eu
    hash=$(cat "{{game}}/GameAssembly.dll" "{{metadata}}" | sha256sum | cut -d' ' -f1)
    if cat data/dump/*/source.sha256 2>/dev/null | grep -qxF "$hash"; then
        echo "dump up to date"
        exit 0
    fi
    tmp=data/dump/.new
    rm -rf "$tmp"
    mkdir -p "$tmp"
    dotnet "{{dumper}}" "{{game}}/GameAssembly.dll" "{{metadata}}" "$tmp"
    version=$(sed -n 's/.*const string StableManifestVersion = "\(.*\)";/\1/p' "$tmp/dump.cs")
    [ -n "$version" ] || { echo "no StableManifestVersion in the dump" >&2; exit 1; }
    out=data/dump/$version
    rm -rf "$out"
    mv "$tmp" "$out"
    echo "$hash" > "$out/source.sha256"
    echo "dumped $version -> $out"

# Regenerate schema/schema.json (the static data's) and schema/events.json (the events the
# reader takes as the game's JSON) from an IL2CPP dump (default: the newest in data/dump)
[private]
schema dump_cs="":
    #!/usr/bin/env bash
    set -eu
    dump_cs="{{dump_cs}}"
    [ -n "$dump_cs" ] || dump_cs=$(ls -d data/dump/*/ | sort -V | tail -1)dump.cs
    uv run python -m tools.gen_schema "$dump_cs" schema/schema.json
    uv run python -m tools.gen_schema "$dump_cs" schema/events.json \
        --root UpdatableGlobalEventsData --root GlobalEventInterfaceSettingsDto --attribute Json

# Compare the computed base stats (optimiser/levels.py) with a raider oracle table
check-levels oracle="data/game/base_stats_6_60.json":
    uv run python -m tools.check_levels oracle "{{oracle}}" data/game/hero_types.json

# The hit model (optimiser/hit.py) against the game's own code, run in an emulator
# (tests/test_game_code.py), with the dump of the installed GameAssembly.dll
test-game *args:
    #!/usr/bin/env bash
    set -eu
    hash=$(cat "{{game}}/GameAssembly.dll" "{{metadata}}" | sha256sum | cut -d' ' -f1)
    dump=$(dirname "$(grep -lxF "$hash" data/dump/*/source.sha256 | head -1)")
    [ "$dump" != . ] || { echo "no dump of the installed game: just dump" >&2; exit 1; }
    GAME_ASSEMBLY="{{game}}/GameAssembly.dll" GAME_METADATA="{{metadata}}" GAME_DUMP="$dump" \
        uv run --group dev --group emulate pytest tests/test_game_code.py "$@"

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

# The game's own battle engine (host/) on a fight's setup, on auto, once per seed (seed 0 is the
# setup's own: a captured fight replays exactly): each champion's result-screen rows and the
# spread, and which seeds lost (just fight data/captures/setups/<file>.json 300 6: the seeds split
# over 6 host processes at once)
fight setup seeds="600" jobs="6":
    #!/usr/bin/env bash
    set -eu
    rm -rf data/cache/host/results && mkdir -p data/cache/host/results
    just host
    per=$(( ({{seeds}} + {{jobs}} - 1) / {{jobs}} ))
    for (( job = 0; job < {{jobs}}; job++ )); do
        first=$(( job * per )); count=$(( {{seeds}} - first < per ? {{seeds}} - first : per ))
        [ "$count" -gt 0 ] || break
        HOST_JOB=$job just host-run fight "{{setup}}" "$count" data/cache/host/results "$first" \
            > "data/cache/host/job-$job.log" 2>&1 &
    done
    wait
    uv run python -m optimiser.fights data/cache/host/results

# Any of the account's champions, in what they wear now, against a stage (its id: the enemies
# from its static data) or a captured fight's enemies (its setup's file): their slots built by
# the game's own code, then fought like `fight` (just sim 2072010 22704,16470,21539,16536,21504
# 20 5 — skill settings from that saved team, else the captured fight's, else auto's defaults)
sim against champions seeds="600" preset="":
    #!/usr/bin/env bash
    set -eu
    work=data/cache/host
    ids=$(echo "{{champions}}" | tr ',' ' ')
    uv run python -m optimiser.setups request "$work/request.json" $ids
    just host-run build "$work/request.json" "$work/parts.json"
    uv run python -m optimiser.setups assemble "{{against}}" "$work/parts.json" "$work/setup.json" $ids \
        $([ -n "{{preset}}" ] && echo --preset "{{preset}}")
    just fight "$work/setup.json" "{{seeds}}"

# The battle host on a command (fight, build) with POSIX paths: plain Wine in a prefix of its
# own, the static data a fresh copy each run (the game's loader deletes a cache it can't load)
[private]
host-run command *args: host
    #!/usr/bin/env bash
    set -eu
    work=data/cache/host
    local_low="$work/LocalLow${HOST_JOB:+-$HOST_JOB}"  # a copy per job: one may delete its own
    rm -rf "$local_low" && mkdir -p "$local_low" "$work/prefix"
    cp -r "{{static_cache}}" "$local_low/"
    win() { echo "Z:$(realpath -m "$1")" | sed 's#/#\\#g'; }
    shift
    paths=()
    for arg in "$@"; do
        case "$arg" in */*) paths+=("$(win "$arg")") ;; *) paths+=("$arg") ;; esac
    done
    WINEPREFIX="$(realpath "$work/prefix")" WINEDEBUG=-all wine host/target/x86_64-pc-windows-gnu/release/raid-host.exe \
        "$(win "{{game}}/GameAssembly.dll")" "$(win "{{game}}/Raid_Data/il2cpp_data")" "$(win "$local_low")" \
        "$(ls "{{static_cache}}" | sort -V | tail -1)" "$(win data/captures/snapshot.json)" "{{command}}" "${paths[@]}"

# Capture the next fight in the game whole: its setup as it starts (from the game's registry,
# read only) into data/captures/setups, its result once it's over (`just results`, polled), then
# the replay checked against it (`just check-capture`). Ctrl-C stops
capture:
    #!/usr/bin/env bash
    set -eu
    setup=$(uv run python -m tools.capture_setup "{{RAID_PREFIX}}/user.reg" data/captures/setups | tail -1)
    id=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["z"])' "$setup")
    echo "waiting for the fight to finish (its result, $id)" >&2
    until [ -f "data/captures/results/$id.json" ]; do
        sleep 15
        just results >/dev/null 2>&1 || true
    done
    just check-capture "$setup"

# The battle host (host/), built for Windows like the reader
[private]
host:
    cd host && cargo build --release
