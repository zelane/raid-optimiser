"""
test_equip.py - a build's Equip, checked again against the account as it is when pressed
(`service.results.check_equip`): a build found before its pieces moved mustn't take them from a
champion its gear rules keep it from.

- `test_locked_since`: a piece now on a champion locked above the run's level is refused
- `test_rules_carried`: a run's form gives its gear fields only (`gear_fields`)
- `test_filter_form_round_trips`: a filter's fields (`filter_form`, Team gear's) parse back to it
- `test_free_pieces_pass`: loose pieces, the champion's own, teammates', and a button sending no
  rules (accessory swaps) all pass
"""

from dataclasses import replace

import pytest

from optimiser.account import Account, Champion
from optimiser.paths import GAME, SCHEMA, SNAPSHOT
from webui.forms.request import Equip, filter_form, gear_fields, parse_equip
from webui.service.results import check_equip


@pytest.fixture(scope="module")
def account() -> Account:
    if not SNAPSHOT.exists():
        pytest.skip("no account snapshot (just read)")

    from optimiser.account import load_account

    return load_account(SNAPSHOT, GAME, SCHEMA)


def two_champions(account: Account) -> tuple[Champion, Champion]:
    first, second = list(account.champions.values())[:2]
    return first, second


def equip(account: Account, pieces: list[int], form: dict[str, str], locks) -> Equip:
    fields = {**form, "artifact_ids": ",".join(map(str, pieces))}
    parsed = parse_equip(fields, account, locks, ())
    assert isinstance(parsed, Equip)
    return parsed


def test_locked_since(account: Account) -> None:
    taker, holder = two_champions(account)
    piece = account.artifacts[0].id
    moved = replace(account, owners={**account.owners, piece: holder.id})
    rules = {"locked": "on", "lock_level": "4"}

    refused = check_equip(equip(moved, [piece], rules, {holder.id: 5}), moved, taker)
    assert refused and holder.name in refused and "locked at 5" in refused

    assert check_equip(equip(moved, [piece], rules, {holder.id: 4}), moved, taker) is None


def test_rules_carried() -> None:
    form = {"locked": "on", "lock_level": "2", "unworn_only": "on", "min_SPD": "200"}
    assert gear_fields(form) == {"locked": "on", "lock_level": "2", "unworn_only": "on"}


def test_filter_form_round_trips(account: Account) -> None:
    rules = {"locked": "on", "lock_level": "3", "unworn_only": "on"}
    parsed = equip(account, [account.artifacts[0].id], rules, {})
    assert filter_form(parsed.gear) == rules


def test_free_pieces_pass(account: Account) -> None:
    taker, mate = two_champions(account)
    loose, own, mates = (artifact.id for artifact in account.artifacts[:3])
    owners = {**account.owners, own: taker.id, mates: mate.id}
    owners.pop(loose, None)
    moved = replace(account, owners=owners)
    strict = {"unworn_only": "on"}
    pieces = [loose, own, mates]

    with_team = replace(equip(moved, pieces, strict, {}), team=frozenset({mate.id}))
    assert check_equip(with_team, moved, taker) is None
    assert check_equip(equip(moved, pieces, strict, {}), moved, taker)
    assert check_equip(equip(moved, pieces, {}, {mate.id: 5}), moved, taker) is None
