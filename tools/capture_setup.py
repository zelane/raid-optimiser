"""capture_setup.py - the setup of the next fight the game starts, saved for the battle host
(`just fight`). While a fight runs the game keeps its setup in PlayerPrefs
(`BattleSetupsCache`, key `BattleSetupCache_<user id>`): under Wine, a value in the prefix's
`user.reg`, base64 of gzip of the game's JSON, a list of setups (often, not always, empty
between fights). The registry file is only read.

- `main`: wait for a new fight, save its setup as `<out>/<time>-<stage>.json`
- `cached_setups`, `saved_ids`: what the registry holds now, and the fights already saved

A fight is new when its setup's id (`z`, a GUID per fight) is neither cached when the wait starts
(the cache isn't always emptied between fights, and auto repeats keep it) nor already saved.

    uv run python -m tools.capture_setup <prefix>/user.reg data/captures/setups
"""

import base64
import gzip
import json
import re
import time
from datetime import datetime
from pathlib import Path

import click

CACHE_KEY = re.compile(r'"BattleSetupCache_[^"]+"=hex:((?:[0-9a-f]{2},?\\?\s*)+)')
POLL_SECONDS = 5


@click.command()
@click.argument("registry", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("out", type=click.Path(file_okay=False, path_type=Path))
def main(registry: Path, out: Path) -> None:
    seen = saved_ids(out) | {s.get("z") for s in cached_setups(registry)}
    click.echo("waiting for a new fight to start in the game (Ctrl-C stops)", err=True)

    while not (new := [s for s in cached_setups(registry) if s.get("z") not in seen]):
        time.sleep(POLL_SECONDS)

    out.mkdir(parents=True, exist_ok=True)

    for setup in new:
        path = out / f"{datetime.now():%Y%m%d-%H%M%S}-{setup['i']}.json"
        path.write_text(json.dumps(setup))
        click.echo(f"saved stage {setup['i']}'s setup to {path}", err=True)
        click.echo(path)  # for `just capture`, which waits for the fight's result


def saved_ids(out: Path) -> set[str]:
    return {json.loads(path.read_text()).get("z") for path in out.glob("*.json")}


def cached_setups(registry: Path) -> list[dict]:
    """The setups the game holds now (none between fights; Wine writes the registry file a
    few seconds after a change)."""
    match = CACHE_KEY.search(registry.read_text(encoding="utf-8", errors="replace"))

    if not match:
        return []

    raw = bytes(int(pair, 16) for pair in re.findall(r"[0-9a-f]{2}", match.group(1)))
    return json.loads(gzip.decompress(base64.b64decode(raw.rstrip(b"\0"))))


if __name__ == "__main__":
    main()
