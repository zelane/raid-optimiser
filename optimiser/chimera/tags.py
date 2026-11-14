"""
tags.py - the Chimera as a target (`optimiser.teams.Target`): what each of its forms is immune
to, and the targets its trials' needs (`form_target`) and the extras (`ANY_FORM`) are met
against.

- `CHIMERA`, `BOSS_IMMUNE`, `FORM_ALLOWS`, `NEVER_LANDS`, `only_in`, `immune_to`: the
  Chimera's immunities, by form
- `form_target`, `ANY_FORM`: its targets
"""

from optimiser.teams.tags import Side, Tag, Target

CHIMERA = "the Chimera"  # what labels call it

# What every form of the Chimera is immune to (its Almighty passives: control debuffs), and
# what each form lets through all the same (Almighty Ram, Almighty Viper).
BOSS_IMMUNE = frozenset(
    {
        "Petrification",
        "Stun",
        "Freeze",
        "Sleep",
        "Provoke",
        "BlockActiveSkills",
        "BlockPassiveSkills",
        "Fear",
        "Enfeeble",
        "Ensnare",
        "Fatigue",
        "HuntersMark",
        "Nullifier",
    }
)

FORM_ALLOWS = {"Ram": frozenset({"Fear"}), "Snake": frozenset({"BlockActiveSkills"})}
# Debuffs no form takes: never worth bringing.
NEVER_LANDS = BOSS_IMMUNE - frozenset().union(*FORM_ALLOWS.values())


def only_in(tag: Tag) -> tuple[str, ...]:
    """The forms a debuff the Chimera is otherwise immune to lands in (none: any form)."""
    if tag.side != Side.DEBUFF or tag.name not in BOSS_IMMUNE:
        return ()

    return tuple(form for form, allows in FORM_ALLOWS.items() if tag.name in allows)


def immune_to(form: str) -> frozenset[str]:
    return BOSS_IMMUNE - FORM_ALLOWS.get(form, frozenset())


def form_target(form: str) -> Target:
    """The Chimera in a form: a trial's needs are met against it."""
    return Target(CHIMERA, immune_to(form))


# The extras are wanted in no form in particular: every form's immunities.
ANY_FORM = Target(CHIMERA, BOSS_IMMUNE)
