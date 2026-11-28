"""
battle.py - what a battle adds to a champion's stats besides their own: stat buffs on them and
the leader's aura. Both are bonuses on base stats, as gear's percentages are (`stats.resolve`:
ATK, DEF, SPD and HP by a share of base; C.RATE and C.DMG add; ACC and RES flat), so a solve adds
them to the champion's constant and every goal sees them.

The buffs' strengths are the game's, in their status names (`IncreaseSpeed30`: +30 % SPD). That
ACC and RES buffs add flat points, not a share of base, isn't read from the game's code yet.

- `FLAT_BUFFS`, `Buff`, `BUFFS`: the stat buffs, two strengths per stat (one at a time)
- `FACTION_WARS`, `Leader`: a champion's aura, one of their type's (a mythical has one per form)
- `Battle`: what a solve assumes (`bonuses`: as the stat model takes them)
- `auras_reaching`: the account's leaders whose auras reach a champion
"""

from dataclasses import dataclass

from optimiser.account import Account, Champion
from optimiser.tables import Aura, Bonus, Stat

FLAT_BUFFS = (Stat.ACC, Stat.RES)  # +25 is 25 points, not 25 % of base
FACTION_WARS = "Fractions"  # the game's area name


@dataclass(frozen=True)
class Buff:
    """A stat buff: `status` is the game's name, `percent` its strength as the name says."""

    status: str
    stat: Stat
    percent: int

    def bonus(self) -> Bonus:
        if self.stat in FLAT_BUFFS:
            return Bonus(self.stat, self.percent, absolute=True)

        return Bonus(self.stat, self.percent / 100, absolute=False)


BUFFS: dict[Stat, tuple[Buff, Buff]] = {
    stat: (Buff(f"Increase{name}{small}", stat, small), Buff(f"Increase{name}{large}", stat, large))
    for stat, name, small, large in [
        (Stat.ATK, "Attack", 25, 50),
        (Stat.DEF, "Defence", 30, 60),
        (Stat.SPD, "Speed", 15, 30),
        (Stat.ACC, "Accuracy", 25, 50),
        (Stat.RES, "Resistance", 25, 50),
        (Stat.CR, "CriticalChance", 15, 30),
        (Stat.CD, "CriticalDamage", 15, 30),
    ]
}


@dataclass(frozen=True)
class Leader:
    """A champion leading with one of their type's auras: `number`, 0 first."""

    champion: Champion
    number: int
    aura: Aura

    @property
    def key(self) -> str:
        """How a form names it."""
        return f"{self.champion.id}:{self.number}"


@dataclass(frozen=True)
class Battle:
    """Buffs on the champion (at most one per stat) and a leader's aura, if any."""

    buffs: tuple[Buff, ...] = ()
    leader: Leader | None = None

    def bonuses(self) -> tuple[Bonus, ...]:
        aura = (self.leader.aura.bonus,) if self.leader else ()
        return (*(buff.bonus() for buff in self.buffs), *aura)


def auras_reaching(account: Account, champion: Champion) -> list[Leader]:
    """A leader per champion type and aura that reaches `champion` (the type's highest copy,
    the champion themselves among them: an aura reaches its leader too). A Faction Wars aura
    reaches only the leader's faction: a crypt admits no other."""
    leaders: dict[tuple[int, int], Leader] = {}
    highest_first = sorted(account.champions.values(), key=lambda c: (-c.grade, -c.level, c.id))

    for leader in highest_first:
        hero_type = account.tables.hero_types.get(leader.type_id)
        auras = hero_type.auras if hero_type else ()

        for number, aura in enumerate(auras):
            crypt_mate = aura.area != FACTION_WARS or leader.faction == champion.faction

            if champion.reached_by(aura) and crypt_mate:
                leaders.setdefault((leader.type_id // 10, number), Leader(leader, number, aura))

    return list(leaders.values())
