"""
cover.py - a team against the trials: which it clears (each trial's needs met, and the one
above it cleared), who brings what each needs, the champions it can't do without, and how far
it can count on it all (`team_score`: the mean of its needs' scores; a team's sources of a tag
combine, two 50% ones making 75%).

- `NeedCover`, `TrialCover`, `Member`, `Lineup`: a team against the trials
- `lineup_of`, `trial_covers`, `need_cover` (`bare_cover`, `best_rating`): who covers what
- `core_of`, `met_count`: the champions it needs
- `team_score`, `need_score`, `team_rating`, `ranking`: how far it can count on them
"""

from dataclasses import dataclass, replace

from optimiser.account import Champion
from optimiser.chimera.kits import Kit, Rating, strength
from optimiser.chimera.tags import Side, Tag, plain_label, tag_label
from optimiser.chimera.trials import (
    AnyOf,
    Distinct,
    Given,
    Goals,
    Requirement,
    counts_toward,
    stacking_tags,
)
from optimiser.enemies import Trial


@dataclass(frozen=True)
class NeedCover:
    """A need, whether the team meets it, who in the team brings what it asks, `asks`: the
    tags that would do (none for a count), `brought`: for a count, the effects the team
    brings toward it, and `notes`: what else meets it (the gear)."""

    label: str
    met: bool
    by: tuple[Champion, ...]
    notes: tuple[str, ...] = ()
    asks: tuple[Tag, ...] = ()
    brought: tuple[Tag, ...] = ()
    score: float = 0.0  # how far the team can count on it (`need_score`)
    ratings: tuple[Rating, ...] = ()  # each of `by`'s best source of it


@dataclass(frozen=True)
class TrialCover:
    """A trial and whether the team clears it: its needs met, and the one above it cleared."""

    trial: Trial
    met: bool
    needs: tuple[NeedCover, ...]


@dataclass(frozen=True)
class Member:
    """A champion in a slot: `chosen` by the user (else the search's suggestion), and
    `needed`: dropping it clears fewer trials."""

    champion: Champion
    chosen: bool
    needed: bool


@dataclass(frozen=True)
class Lineup:
    """The team's slots (`TEAM_SIZE`, None when open), the trials it clears, and who brings
    the debuffs wanted besides (`Goals.extras`)."""

    slots: tuple[Member | None, ...]
    trials: tuple[TrialCover, ...]
    extras: tuple[NeedCover, ...]
    score: float  # `team_score`

    @property
    def cleared(self) -> int:
        return sum(cover.met for cover in self.trials)


def met_count(kits: list[Kit], goals: Goals) -> int:
    """The trials the team clears and the extras it brings."""
    cleared = sum(cover.met for cover in trial_covers(kits, goals))
    return cleared + sum(need_cover(r, kits).met for r in goals.extra_requirements)


def lineup_of(
    slots: list[Kit | None],
    suggested: set[int],
    goals: Goals,
) -> Lineup:
    """The slots as members (`suggested`: the ids of the kits the search added), what the
    team clears, and who brings the extras."""
    kits = [kit for kit in slots if kit]
    covers = trial_covers(kits, goals)
    extras = tuple(need_cover(r, kits) for r in goals.extra_requirements)
    core = core_of(kits, goals, sum(c.met for c in covers) + sum(e.met for e in extras))
    members = tuple(
        Member(kit.champion, id(kit) not in suggested, kit in core) if kit else None
        for kit in slots
    )
    return Lineup(members, covers, extras, team_score(kits, goals))


def trial_covers(kits: list[Kit], goals: Goals) -> tuple[TrialCover, ...]:
    met: dict[int, bool] = {}
    covers = []

    for trial in goals.trials:
        need_covers = tuple(need_cover(r, kits) for r in goals.trial_requirements(trial))
        above = met.get(trial.requires, True) if trial.requires else True
        met[trial.skill] = above and all(n.met for n in need_covers)
        covers.append(TrialCover(trial, met[trial.skill], need_covers))

    return tuple(covers)


def need_cover(requirement: Requirement, kits: list[Kit]) -> NeedCover:
    """Whether and how the team meets the need, scored (`need_score`), each champion bringing
    it with its best source's `Rating`."""
    cover = bare_cover(requirement, kits)
    ratings = tuple(best_rating(kit, requirement) for kit in kits if kit.champion in cover.by)
    return replace(cover, score=need_score(requirement, kits), ratings=ratings)


def bare_cover(requirement: Requirement, kits: list[Kit]) -> NeedCover:
    need, form = requirement.need, requirement.form
    match need:
        case Given(need=inner, gear=gear):
            cover = bare_cover(replace(requirement, need=inner), kits)
            return NeedCover(cover.label, True, (), (f"{gear} (any champion)",), cover.asks)

        case AnyOf(tags=tags):
            by = tuple(kit.champion for kit in kits if kit.tags & tags)
            asks = tuple(sorted(tags, key=tag_label))
            return NeedCover(" or ".join(tag_label(tag) for tag in asks), bool(by), by, (), asks)

        case Distinct(side=side, count=count, instances=instances):
            counted = [k for k in kits if any(counts_toward(t, need, form) for t in k.tags)]
            brought = tuple(
                sorted(
                    {t for k in counted for t in k.tags if counts_toward(t, need, form)},
                    key=plain_label,
                )
            )
            where = "on the Chimera" if side == Side.DEBUFF else "on the team"

            if instances:
                poisoners = tuple(k.champion for k in kits if k.tags & stacking_tags(need))
                label = f"{count} {side}s {where} (Poisons stack: any Poison will do, if fast)"

                if poisoners:
                    return NeedCover(label, True, poisoners, brought=tuple(stacking_tags(need)))

                by = tuple(k.champion for k in counted)
                return NeedCover(label, len(brought) >= count, by, brought=brought)

            label = f"{count} different {side}s {where}"
            by = tuple(k.champion for k in counted)
            return NeedCover(label, len(brought) >= count, by, brought=brought)


def best_rating(kit: Kit, requirement: Requirement) -> Rating:
    """The champion's best source of what the need asks."""
    need, form = requirement.need, requirement.form
    match need:
        case Given(need=inner):
            return best_rating(kit, replace(requirement, need=inner))
        case AnyOf(tags=tags):
            useful = [kit.ratings[t] for t in tags if t in kit.ratings]
        case Distinct(instances=instances):
            stacking = stacking_tags(need) if instances else frozenset()
            useful = [
                rating
                for tag, rating in kit.ratings.items()
                if counts_toward(tag, need, form) or tag in stacking
            ]

    return max(useful, key=lambda r: r.score)


def team_score(kits: list[Kit], goals: Goals) -> float:
    """How far the team can count on what the trials and the extras need: the mean of their
    `need_score`s (trials needing nothing left out), 0 to 1."""
    requirements = goals.requirements
    if not requirements:
        return 0.0

    return sum(need_score(r, kits) for r in requirements) / len(requirements)


def need_score(requirement: Requirement, kits: list[Kit]) -> float:
    """0 to 1: for one of several tags, the team's best; for a count, the mean of its best
    `count` different ones (a Poison stacks: its own score meets an instance count); gear, its
    own rating."""
    need, form = requirement.need, requirement.form
    match need:
        case Given(score=score):
            return score

        case AnyOf(tags=tags):
            return max((team_rating(kits, tag) for tag in tags), default=0.0)

        case Distinct(count=count, instances=instances):
            counting = {t for kit in kits for t in kit.tags if counts_toward(t, need, form)}
            best = sorted((team_rating(kits, tag) for tag in counting), reverse=True)[:count]
            spread = sum(best) / count

            if not instances:
                return spread

            stacks = max((team_rating(kits, tag) for tag in stacking_tags(need)), default=0.0)
            return max(spread, stacks)


def team_rating(kits: list[Kit], tag: Tag) -> float:
    """How far the team can count on the tag: its sources together (two 50% ones, 75%)."""
    missing = 1.0

    for kit in kits:
        if rating := kit.ratings.get(tag):
            missing *= 1 - rating.score

    return 1 - missing


def ranking(kits: list[Kit], goals: Goals) -> tuple[float, int, float]:
    """The best scored team first, then the one needing fewest champions, then strongest."""
    return (-team_score(kits, goals), len(kits), -sum(strength(k.champion) for k in kits))


def core_of(kits: list[Kit], goals: Goals, met: int) -> list[Kit]:
    """The champions the team can't do without: dropping each in turn (and keeping it out if
    the team still meets as much: `met_count`), those it can't drop."""
    core = list(kits)

    for kit in list(kits):
        without = [k for k in core if k is not kit]
        if met_count(without, goals) >= met:
            core = without

    return core
