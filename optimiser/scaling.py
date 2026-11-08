"""
scaling.py - what the roster's 6★ champions scale off, and the champion types of a faction's
own that come of it. Accessories are faction-locked, so a faction whose damage dealers scale
off two stats (Rotos: 2.1·ATK + 0.19·HP) or whose supports heal and shield off ATK wants
pieces the standard types (`optimiser.roles`) undervalue.

A formula's pull on a stat is how much one roll of it adds (a % roll of the champion's base
for ATK/HP/DEF, a flat roll for ACC/RES/SPD), at typical geared stats; a champion's pull
sums its formulas' shapes (each against its own strongest stat): damage hits and bombs for
damage dealers, heals, shields and revives for supports (the game's Support role). Champions
whose pull is all one of HP/ATK/DEF are the standard types already; the rest get a type of
their faction's own, one per distinct shape.

Mythicals count each form as a champion of its own: some want the same stats in both, others
are geared for one form, which `OVERRIDES` can say. The champion-exceptions skill
(`.claude/skills/champion-exceptions`) and `tools/scaling_report.py` find what needs one.

- `TYPICAL`, `ROLL`, `MIXED`, `MINOR`: what's typical, and what counts as a second stat
- `Wearer`, `Pull`: a champion in one form, and what it pulls on
- `Skip`, `Weigh`, `Override`, `OVERRIDES`: exceptions, by champion name and form
- `faction_types`: the roster's types
- `wearers`, `wearer_type`, `wearer_pull`, `formula_pull`, `evaluate`, `own_type`,
  `damage_type`, `support_type`, `build_type`, `type_label`, `round_weight`: its steps
"""

import ast
import re
from dataclasses import dataclass

from optimiser.account import Account, Champion, HeroForm, Slot, Stat
from optimiser.labels import STAT_LABELS
from optimiser.roles import (
    DEFAULT_TYPE_WEIGHTS,
    SUPPORT_BALANCE,
    TYPE_STATS,
    ChampionType,
    Kind,
    Mains,
    TypeKey,
)

BODY = (Stat.ATK, Stat.HP, Stat.DEF)
TOKENS = {"ATK": Stat.ATK, "HP": Stat.HP, "DEF": Stat.DEF, "ACC": Stat.ACC, "RES": Stat.RES}
TOKENS |= {"SPD": Stat.SPD}
TYPICAL = {Stat.ACC: 250.0, Stat.RES: 250.0, Stat.SPD: 250.0}  # flat stats, geared
GEARED = 2.2  # ATK/HP/DEF geared, against base
ROLL = {Stat.ACC: 10.5, Stat.RES: 10.5, Stat.SPD: 5.5}  # flat rolls; ATK/HP/DEF: 6% of base
BODY_ROLL = 0.06
MIXED = 0.3  # a second stat pulling this much of the first makes a mixed type
MINOR = 0.1  # pulls below this are left out
DAMAGE_KINDS = {"ApplyDebuff"}  # bombs
SUPPORT_KINDS = {"Heal", "ApplyBuff", "Revive"}
GRADE = 6


@dataclass(frozen=True)
class Wearer:
    """A champion in one of its forms (1 for most; mythicals have 2)."""

    champion: Champion
    form_number: int
    form: HeroForm
    forms: int  # how many the champion has

    def name(self) -> str:
        """ "Kurosa the Covetous (form 2)" for a mythical, the plain name otherwise."""
        name = self.champion.name
        return f"{name} (form {self.form_number})" if self.forms > 1 else name


@dataclass(frozen=True)
class Pull:
    """Per stat, against the strongest (1.0); empty when nothing scales."""

    damage: dict[Stat, float]
    support: dict[Stat, float]


@dataclass(frozen=True)
class Skip:
    """The champion (in this form) gets no type of its own: say, a form nobody gears for."""

    reason: str


@dataclass(frozen=True)
class Weigh:
    """The type to use instead of the one its formulas give (weights as the standard types'
    are: average 6★ rolls per stat)."""

    label: str
    kind: Kind
    weights: dict[Stat, float]
    mains: Mains
    reason: str


type Override = Skip | Weigh

# (champion name, form number) -> the exception. Found with the champion-exceptions skill;
# each says why, so it can be checked again after the champion is reworked.
GHAROL = Weigh(
    label="HP+ATK+ACC damage",
    kind=Kind.DAMAGE,
    weights={Stat.HP: 5, Stat.ATK: 3, Stat.ACC: 4, Stat.CD: 5, Stat.SPD: 4},
    mains=(
        (Slot.RING, (Stat.HP, Stat.ATK)),
        (Slot.AMULET, (Stat.CD,)),
        (Slot.BANNER, (Stat.HP, Stat.ACC, Stat.ATK)),
    ),
    reason="geared for both forms (form 1 HP, form 2 ATK+HP) and wants high ACC, which no"
    " formula of his reads",
)

OVERRIDES: dict[tuple[str, int], Override] = {
    ("Gharol Bloodmaul", 1): GHAROL,
    ("Gharol Bloodmaul", 2): GHAROL,
    ("Nais the Shadowthief", 1): Skip("geared for form 2 (HP); form 1's HP+ATK mix doesn't count"),
    ("Toshiro the Bloody", 2): Skip("geared for form 1 (ATK+HP); form 2 is standard HP anyway"),
}


def faction_types(account: Account) -> tuple[ChampionType, ...]:
    """Types of a faction's own, from its 6★ champions' forms; forms alike share one."""
    by_key: dict[str, ChampionType] = {}

    for wearer in wearers(account):
        if (own := wearer_type(wearer, account)) is None:
            continue

        if (known := by_key.get(own.key)) is not None:
            own = ChampionType(
                **{**known.__dict__, "champions": (*known.champions, *own.champions)}
            )

        by_key[own.key] = own

    return tuple(by_key.values())


def wearers(account: Account) -> list[Wearer]:
    """Each 6★ champion type the account has, in each of its forms, by name."""
    seen: set[int] = set()
    found = []

    for champion in sorted(account.champions.values(), key=lambda c: c.name):
        if champion.grade < GRADE or champion.type_id in seen:
            continue

        seen.add(champion.type_id)
        forms = account.tables.hero_forms.get(champion.type_id, ())
        found += [Wearer(champion, n, form, len(forms)) for n, form in enumerate(forms, start=1)]

    return found


def wearer_type(wearer: Wearer, account: Account) -> ChampionType | None:
    """Its exception if it has one, else what its formulas give."""
    match OVERRIDES.get((wearer.champion.name, wearer.form_number)):
        case Skip():
            return None

        case Weigh(label=label, kind=kind, weights=weights, mains=mains):
            return build_type(wearer, kind, weights, mains, label)

        case None:
            return own_type(wearer, wearer_pull(wearer, account))


def wearer_pull(wearer: Wearer, account: Account) -> Pull:
    tables = account.tables
    base = wearer.form.base_6_60 or tables.base_6_60.get(wearer.champion.type_id, {})
    damage: dict[Stat, float] = {}
    support: dict[Stat, float] = {}

    for skill_id in wearer.form.skills:
        if (skill := tables.skills.get(skill_id)) is None:
            continue

        for hit in skill.hits:
            add_pull(damage, formula_pull(hit.formula, base), hit.count)

        for effect in skill.scaling:
            target = damage if effect.kind in DAMAGE_KINDS else support

            if effect.kind in DAMAGE_KINDS | SUPPORT_KINDS:
                add_pull(target, formula_pull(effect.formula, base), 1)

    return Pull(normalised(damage), normalised(support))


def add_pull(total: dict[Stat, float], pull: dict[Stat, float], times: int) -> None:
    """Each effect counts its shape, not its size: a one-off full heal (`HP*1`) mustn't
    outweigh a champion's every other heal."""
    for stat, share in normalised(pull).items():
        total[stat] = total.get(stat, 0) + share * times


def normalised(pull: dict[Stat, float]) -> dict[Stat, float]:
    strongest = max(pull.values(), default=0)

    if strongest <= 0:
        return {}

    return {stat: amount / strongest for stat, amount in pull.items() if amount > 0}


def formula_pull(formula: str, base: dict[Stat, float]) -> dict[Stat, float]:
    """How much one roll of each stat the formula reads adds to it; {} if it can't be read."""
    stats = {stat: base.get(stat, 0) * GEARED for stat in BODY} | TYPICAL
    rolls = {stat: base.get(stat, 0) * BODY_ROLL for stat in BODY} | ROLL

    if (now := evaluate(formula, stats)) is None:
        return {}

    pull = {}

    for stat in {TOKENS[t] for t in re.findall(r"[A-Z_]+", formula) if t in TOKENS}:
        rolled = evaluate(formula, {**stats, stat: stats[stat] + rolls[stat]})
        if rolled is not None and rolled > now:
            pull[stat] = rolled - now

    return pull


ALLOWED = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.Constant,
    ast.operator,
    ast.unaryop,
    ast.boolop,
    ast.cmpop,
)


def evaluate(formula: str, stats: dict[Stat, float]) -> float | None:
    """The formula's value with the caster's stats in, anything else (the target's stats,
    battle counters) at 0; None for what can't be read."""
    expression = formula

    while (simpler := re.sub(r"[A-Za-z_]\w*\([^()]*\)", "0", expression)) != expression:
        expression = simpler  # calls (counters of the battle) count nothing

    expression = re.sub(r"!(?!=)", " not ", expression).replace("||", " or ")
    expression = expression.replace("&&", " and ")
    expression = re.sub(
        r"\b[A-Za-z_]\w*\b",
        lambda m: (
            m.group(0)
            if m.group(0) in ("not", "or", "and")
            else str(stats.get(TOKENS[m.group(0)], 0) if m.group(0) in TOKENS else 0)
        ),
        expression,
    )

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return None

    if not all(isinstance(node, ALLOWED) for node in ast.walk(tree)):
        return None

    try:
        return float(eval(compile(tree, "<formula>", "eval"), {"__builtins__": {}}))
    except (ArithmeticError, TypeError, ValueError):
        return None


def own_type(wearer: Wearer, pull: Pull) -> ChampionType | None:
    """None when a standard type covers the champion in this form."""
    if wearer.form.role == "Support":
        return support_type(wearer, pull.support) if pull.support else None

    return damage_type(wearer, pull.damage) if pull.damage else None


def damage_type(wearer: Wearer, pull: dict[Stat, float]) -> ChampionType | None:
    body = [stat for stat in BODY if pull.get(stat, 0) >= MIXED]
    other = [stat for stat in pull if stat not in BODY and pull[stat] >= MIXED]

    if len(body) <= 1 and not other:
        return None

    weights = {Stat.CD: 5.0, Stat.SPD: 4.0, Stat.ACC: 1.0}
    weights |= {s: round_weight(5 * share) for s, share in pull.items() if share >= MINOR}
    suiting = tuple(s for s in BODY if pull.get(s, 0) >= MIXED * 1.5) or tuple(body)
    mains = (
        (Slot.RING, suiting),
        (Slot.AMULET, (Stat.CD,)),
        (Slot.BANNER, (*suiting, Stat.ACC)),
    )
    return build_type(wearer, Kind.DAMAGE, weights, mains, type_label(Kind.DAMAGE, pull))


def support_type(wearer: Wearer, pull: dict[Stat, float]) -> ChampionType | None:
    """Supports heal and shield off HP or DEF mostly, which the standard support covers."""
    leading = max(pull, key=lambda stat: pull[stat])

    if leading in (Stat.HP, Stat.DEF):
        return None

    weights = dict(DEFAULT_TYPE_WEIGHTS[TypeKey.SUPPORT])

    for stat, share in pull.items():
        if share >= MINOR:
            weights[stat] = max(weights.get(stat, 0), round_weight(4 * share))

    suiting = tuple(s for s in BODY if pull.get(s, 0) >= 0.5)
    mains = (
        (Slot.RING, (Stat.HP, Stat.DEF, *suiting)),
        (Slot.AMULET, (Stat.HP, Stat.DEF, *suiting)),
        (Slot.BANNER, (Stat.ACC, Stat.RES, Stat.HP, Stat.DEF, *suiting)),
    )
    return build_type(wearer, Kind.SUPPORT, weights, mains, type_label(Kind.SUPPORT, pull))


def build_type(
    wearer: Wearer, kind: Kind, weights: dict[Stat, float], mains: Mains, label: str
) -> ChampionType:
    ordered = tuple((stat, weights[stat]) for stat in TYPE_STATS if weights.get(stat))
    shape = ",".join(f"{STAT_LABELS[s]}{w:g}" for s, w in ordered)
    return ChampionType(
        key=f"{wearer.champion.faction}:{kind.value}:{shape}",
        label=label,
        kind=kind,
        weights=ordered,
        mains=tuple((slot, tuple(dict.fromkeys(stats))) for slot, stats in mains),
        balance=SUPPORT_BALANCE if kind is Kind.SUPPORT else 0,
        faction=wearer.champion.faction,
        champions=(wearer.name(),),
    )


def type_label(kind: Kind, pull: dict[Stat, float]) -> str:
    """ "ATK+HP damage", "ATK support": the stats it scales off, strongest first."""
    stats = sorted((s for s in pull if pull[s] >= MIXED), key=lambda s: -pull[s])
    return "+".join(STAT_LABELS[s] for s in stats) + f" {kind.value}"


def round_weight(weight: float) -> float:
    return round(weight * 2) / 2
