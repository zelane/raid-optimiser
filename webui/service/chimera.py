"""
chimera.py - the Chimera's part of the team finder: the rotation (the column holding its
mythical materials, the trials the team must clear) and the trial board for the team shown
(Ram, Lion and Snake; Easy, Normal and Hard), each trial lit when the team can clear it in one
fight. `service.teams` searches; this draws what's the Chimera's own.

- `ColumnView`, `TrialView`, `FormRow`, `ChimeraView`: the views
- `chimera_view`: the rotation and what doesn't match the game's data
- `rotation_column`: the column the game's current raid puts the mythical materials in
- `form_rows`, `glance`: the board for a lineup, and an option's at a glance
- `form_note`: where a debuff the Chimera is otherwise immune to lands
- `column_views`, `easy_ram_trials`, `trial_terms`, `level_order`, `trial_view`, `waits_on`:
  their pieces
"""

import re
from dataclasses import dataclass
from datetime import datetime

from optimiser.account import Account
from optimiser.chimera.rotation import mythical_column
from optimiser.chimera.tags import only_in
from optimiser.chimera.trials import ANIMAL_FORMS, LEVELS, PARTS, PLAN_DIFFICULTY
from optimiser.enemies import Enemies, Trial
from optimiser.teams.cover import Lineup, ObjectiveCover
from optimiser.teams.tags import Tag
from webui.service.team import NeedView, need_view
from webui.service.views import asset_url


@dataclass(frozen=True)
class ColumnView:
    """A trial column: the game doesn't name them, so `hint` names its Easy Ram trial's
    statuses; `mythical`: the game's current raid puts the mythical materials in it."""

    part: str
    hint: str
    mythical: bool


@dataclass(frozen=True)
class TrialView:
    """A trial; `waits_on`: the level that must be cleared first, when the team meets this
    one's needs but not that's."""

    level: str
    description: str
    target: str  # "2,000,000", "7"
    damage: bool  # the target is damage (else a count)
    met: bool
    needs: list[NeedView]
    waits_on: str | None = None


@dataclass(frozen=True)
class FormRow:
    form: str
    trials: list[TrialView]  # Easy, Normal, Hard
    cleared: int
    icon_url: str | None  # the game's trial art for the form


@dataclass(frozen=True)
class ChimeraView:
    """The column picked and the ones to pick from, and where the trial needs disagree with
    the game's data (a game update?)."""

    column: str
    columns: list[ColumnView]
    problems: list[str]


def chimera_view(
    enemies: Enemies, column: str, rotation: str | None, problems: tuple[str, ...]
) -> ChimeraView:
    return ChimeraView(column, column_views(enemies, rotation), list(problems))


def rotation_column(account: Account, enemies: Enemies, now: datetime) -> str | None:
    """None when the snapshot has no raid (the game hadn't loaded the Chimera)."""
    raid = account.chimera_raid
    return mythical_column(enemies.chimera, raid, now) if raid else None


def column_views(enemies: Enemies, mythical: str | None) -> list[ColumnView]:
    easy_ram = {t.part: t for t in easy_ram_trials(enemies)}
    return [ColumnView(part, trial_terms(easy_ram[part]), part == mythical) for part in PARTS]


def easy_ram_trials(enemies: Enemies) -> list[Trial]:
    """The trial each column starts with, as the game lists them (alike at every tier)."""
    tier = next(t for t in enemies.chimera.tiers if t.difficulty == PLAN_DIFFICULTY)
    return [t for t in tier.trials if (t.form, t.level) == (ANIMAL_FORMS[0], LEVELS[0])]


def trial_terms(trial: Trial) -> str:
    """The statuses a trial's text names ("[Decrease DEF]", …), in order, once each."""
    return " + ".join(dict.fromkeys(re.findall(r"\[([^\]]+)\]", trial.description)))


def form_note(tag: Tag) -> str | None:
    """Where a debuff the Chimera is otherwise immune to lands: "Ram form only"."""
    forms = only_in(tag)
    return f"{' or '.join(forms)} form only" if forms else None


def glance(rows: list[FormRow]) -> list[tuple[str, list[bool]]]:
    """Each form's trials as met or not, Easy first."""
    return [(row.form, [trial.met for trial in row.trials]) for row in rows]


def form_rows(lineup: Lineup, trials: dict[int, Trial]) -> list[FormRow]:
    """Each form's trials (the lineup's objectives are keyed by their skill), Easy first."""
    covered = [(c, trials[c.objective.key]) for c in lineup.objectives]
    by_form = {form: [(c, t) for c, t in covered if t.form == form] for form in ANIMAL_FORMS}
    return [
        FormRow(
            form,
            [trial_view(c, t) for c, t in sorted(pairs, key=lambda pair: level_order(pair[1]))],
            sum(c.met for c, _ in pairs),
            asset_url("chimera", f"{form}_Hard"),
        )
        for form, pairs in by_form.items()
    ]


def level_order(trial: Trial) -> int:
    return LEVELS.index(trial.level)


def trial_view(cover: ObjectiveCover, trial: Trial) -> TrialView:
    return TrialView(
        level=trial.level,
        description=trial.description,
        target=f"{trial.target:,.0f}",
        damage=trial.damage,
        met=cover.met,
        needs=[need_view(n) for n in cover.needs],
        waits_on=waits_on(cover, trial),
    )


def waits_on(cover: ObjectiveCover, trial: Trial) -> str | None:
    if cover.met or not all(need.met for need in cover.needs):
        return None

    return LEVELS[LEVELS.index(trial.level) - 1]
