"""seed.py - the accessory seeds: the champion types and set fits the store starts from
(`optimiser.accessories.roles`, `scaling`). Without `--reset` it seeds what isn't seeded yet
and lists them; with it, it backs the store up beside itself and seeds both again, losing
what the Weights tab changed (the off-target share stays).

- `main`: the command
- `report`: the types and set fits, as listed

    uv run python -m tools.seed [--reset]
"""

from datetime import datetime

import click

from optimiser.accessories.roles import NO_SET, ChampionType, SetTable
from optimiser.account import load_account
from optimiser.labels import STAT_LABELS
from optimiser.paths import GAME, SCHEMA, SNAPSHOT, STORE
from optimiser.settings import read_champion_types, read_set_table, reseed_accessories
from optimiser.store import backup
from optimiser.tables import ArtifactSet


@click.command()
@click.option("--reset", is_flag=True, help="Back the store up, then seed both again.")
def main(reset: bool) -> None:
    account = load_account(SNAPSHOT, GAME, SCHEMA)

    if reset:
        saved = STORE.with_name(f"{STORE.stem}-{datetime.now():%Y%m%d-%H%M%S}.sqlite.bak")
        backup(STORE, saved)
        click.echo(f"backed up to {saved}")
        types, sets = reseed_accessories(STORE, account)
    else:
        types = read_champion_types(STORE, account)
        sets = read_set_table(STORE, types)

    click.echo(report(types, sets, account.tables.sets))


def report(types: tuple[ChampionType, ...], sets: SetTable, known: dict[int, ArtifactSet]) -> str:
    lines = ["Champion types:"]

    for it in types:
        weights = ", ".join(f"{STAT_LABELS[stat]} {weight:g}" for stat, weight in it.weights)
        faction = f" [{it.faction}]" if it.faction else ""
        lines.append(f"  {it.key:>3} {it.label}{faction} ({it.kind.value}): {weights}")

    labels = {it.key: it.label for it in types}
    lines.append(f"Set fits (off target counts {sets.off_target:g}):")

    for set_id, fit in sets.fits:
        name = known[set_id].name if set_id in known else f"set {set_id}"
        name = "No set" if set_id == NO_SET else name
        off = ", ".join(labels.get(key, f"#{key}") for key in sorted(fit.off, key=int))
        lines.append(f"  {name}: {fit.factor:g}" + (f"; not for {off}" if off else ""))

    return "\n".join(lines)


if __name__ == "__main__":
    main()
