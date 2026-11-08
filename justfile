# raid-export tasks. `just` lists them.

set positional-arguments

dump := env("HOME") / "repo/raider/dump-11.85.5/dump.cs"
oracle_out := "/tmp/raider-oracle.json"
oracle_request_file := "/tmp/raider-oracle-request.txt"

# List the recipes
default:
    @just --list --unsorted

# Capture: mitmproxy tees the HH extractor's upload (extractor + game running)
proxy *args:
    ./run-proxy.sh "$@"

# Re-export the game's static data after a game update (--full for the whole static.json)
static *args:
    ./update-static.sh "$@"

# (Re)build the C# decoder into bin/
decoder:
    dotnet build decoder -c Release -o bin

# Run the optimiser CLI, e.g. just opt "Name" --rank HP,DEF --min SPD=200 --builds 3
opt *args:
    uv run python -m optimiser "$@"

# Start the web UI on http://127.0.0.1:8000
web:
    uv run python -m webui

# Stop the web UI (by port)
web-stop:
    -fuser -k 8000/tcp

# Restart the web UI (needed after Python changes)
web-restart: web-stop web

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

# Regenerate schema/schema.json from an IL2CPP dump (after re-dumping the game)
schema dump_cs=dump:
    python3 -I tools/gen_schema.py "{{dump_cs}}" schema/schema.json

# Write the raider oracle's request file (inject into ~/tmp/inject-test only!)
oracle-request out=oracle_request_file:
    python3 -I tools/oracle_request.py static/hero_types.json "{{out}}"

# Import the raider oracle's output into static/{base_stats_6_60,level_curve}.json
oracle-import input=oracle_out:
    python3 -I tools/oracle_import.py "{{input}}" static/hero_types.json static/
