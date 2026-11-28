"""
test_battle.py - the battle a solve assumes (`optimiser.battle`): stat buffs and a leader's aura
as bonuses on base stats, which auras reach whom, and the form's fields for them.

- `test_buff_bonuses`: SPD by a share of base, ACC flat, C.RATE added
- `test_aura_reaches`: an aura held to an affinity reaches only it
- `test_faction_wars_auras_stay_in_the_crypt`: only the leader's faction is offered one
- `test_solve_sees_the_battle`: the same build, its stats raised by just the battle's bonuses
- `test_parse_battle`: the form's buffs and leader, and the errors for ones that aren't
"""

from dataclasses import replace

import pytest

from optimiser.account import Account
from optimiser.battle import BUFFS, FACTION_WARS, Battle, auras_reaching
from optimiser.paths import GAME, SCHEMA, SNAPSHOT
from optimiser.stats import base_stats, constant_stats, resolve
from optimiser.tables import Aura, Bonus, Stat


@pytest.fixture(scope="module")
def account() -> Account:
    if not SNAPSHOT.exists():
        pytest.skip("no account snapshot (just read)")

    from optimiser.account import load_account

    return load_account(SNAPSHOT, GAME, SCHEMA)


def strongest(stat: Stat):
    return BUFFS[stat][1]


def test_buff_bonuses(account: Account) -> None:
    champion = next(iter(account.champions.values()))
    battle = Battle((strongest(Stat.SPD), strongest(Stat.ACC), strongest(Stat.CR)))
    base = base_stats(champion, account.tables)
    plain = constant_stats(champion, account.tables)
    buffed = constant_stats(champion, account.tables, battle.bonuses())

    assert buffed[Stat.SPD] - plain[Stat.SPD] == pytest.approx(0.3 * base[Stat.SPD])
    assert buffed[Stat.ACC] - plain[Stat.ACC] == pytest.approx(50)
    assert buffed[Stat.CR] - plain[Stat.CR] == pytest.approx(0.3)
    assert buffed[Stat.HP] == plain[Stat.HP]


def test_aura_reaches(account: Account) -> None:
    champion = next(iter(account.champions.values()))
    other = next(e for e in ("Magic", "Force", "Spirit", "Void") if e != champion.element)
    aura = Aura(Bonus(Stat.SPD, 0.2, False), None, champion.element, None, None)

    assert champion.reached_by(aura)
    assert not replace(champion, element=other).reached_by(aura)


def test_faction_wars_auras_stay_in_the_crypt(account: Account) -> None:
    champion = max(account.champions.values(), key=lambda c: (c.grade, c.level))
    leaders = auras_reaching(account, champion)
    crypt_auras = [each for each in leaders if each.aura.area == FACTION_WARS]

    assert all(leader.champion.faction == champion.faction for leader in crypt_auras)


def test_solve_sees_the_battle(account: Account) -> None:
    from optimiser.solve import GearFilter, Request, find_builds

    champion = max(account.champions.values(), key=lambda c: (c.grade, c.level))
    leader = auras_reaching(account, champion)[0]
    battle = Battle((strongest(Stat.SPD),), leader)
    plain_request = Request(
        champion=champion,
        minimums={},
        maximums={},
        set_minimums={},
        ranking=(Stat.SPD,),
        slack=0.0,
        builds=1,
        gear=GearFilter(),
        above_level=8,
    )
    (plain,) = find_builds(account, plain_request)
    (buffed,) = find_builds(account, replace(plain_request, battle=battle))
    base = base_stats(champion, account.tables)

    raised = {stat: 0.0 for stat in Stat}
    raised[Stat.SPD] += 0.3 * base[Stat.SPD]
    raised[leader.aura.bonus.stat] += resolve(leader.aura.bonus, base)

    assert buffed.artifacts == plain.artifacts
    assert buffed.stats == pytest.approx({s: plain.stats[s] + raised[s] for s in Stat})


def test_parse_battle(account: Account) -> None:
    from webui.forms.request import parse_battle

    champion = max(account.champions.values(), key=lambda c: (c.grade, c.level))
    leader = auras_reaching(account, champion)[0]
    errors: list[str] = []
    battle = parse_battle({"buff_SPD": "30", "aura": leader.key}, champion, account, errors)

    assert errors == []
    assert battle == Battle((strongest(Stat.SPD),), leader)

    parse_battle({"buff_SPD": "20", "aura": "0:0"}, champion, account, errors)
    assert len(errors) == 2
