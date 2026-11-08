---
name: champion-exceptions
description: Find 6★ champions (each mythical form apart) whose stat needs the accessory scoring gets wrong, and record exceptions in optimiser/scaling.py OVERRIDES. Use when the user asks to check the roster for stat outliers or exceptions, after new 6★ champions or a game update (champion reworks), or when they name a champion whose gear priority differs from what the formulas say (Joan liking RES, a mythical geared for one form only).
---

# Champion exceptions

Accessories are faction-locked, so the clean-up and the roll/rework lists value each piece
against champion types: the standard five (`optimiser/roles.py`) and a faction's own, made
from its 6★ champions' formulas (`optimiser/scaling.py`). Each mythical form counts as a
champion of its own. Formulas miss things; this skill finds the candidates and records the
user's decisions as exceptions.

## 1. Fresh data

- After a game update, `just static` (rebuilds `static/skills.json`, whose `scaling` field
  holds heal/shield/revive/bomb formulas). The capture must be current for the roster.

## 2. Run the report

```
uv run python -m optimiser.scaling_report            # flagged forms
uv run python -m optimiser.scaling_report --all      # everything
uv run python -m optimiser.scaling_report --name Joan
```

Each row: name (with `(form N)` for mythicals), faction, the form's role, its pull per stat
(damage, support; 1 is its strongest stat), the type it gets (`standard` or its own), flags,
then every formula. Pull is how much one substat roll of a stat adds to the formula at
typical geared stats; each effect counts its shape, not its size.

## 3. Triage, flag by flag

- **forms differ**: a mythical whose forms want different stats. Ask the user which form
  they gear for (or both, when they swap mid-fight). The form not geared for gets `Skip`.
- **own type**: check the derived weights look right for how the champion is played: a
  mixed formula on a skill nobody uses shouldn't drive the faction's gear.
- **utility stat**: ACC/RES/SPD in a formula (Joan's `ATK*(6+RES/1000)`, Karnage's
  `2.3*(ATK+ACC)`). Usually small as damage; the real reason to want the stat is often
  functional, which formulas can't see.
- **target-dependent**: the target's stats or battle counters are read as 0; fine for gear,
  unless the caster's own term is tiny next to them (then the champion barely scales).
- **unreadable**: the formula didn't parse; read it in `static/skills.json` and say whether
  it matters.
- **support, nothing scales**: listed with `--all` only; buffers and debuffers, covered by
  the standard support type.

Don't decide from memory of the game alone: kits change, and what matters is how this user
plays them. Present the candidates (name, what the formulas say, what you suspect) and ask.
Things formulas can't show that the user may raise: stats needed to function (RES for
Joan, ACC thresholds, SPD tuning), passives scaling off a stat, champions used only in
one form or one content.

## 4. Record the decision

In `optimiser/scaling.py`, `OVERRIDES` maps `(champion name, form number)` to:

- `Skip(reason)`: no type of its own for that form.
- `Weigh(label, kind, weights, mains, reason)`: the type to use instead. Weights are average
  6★ rolls per stat, like the standard types (`DEFAULT_TYPE_WEIGHTS` in `roles.py` for
  scale: 5 the main stat, 4 SPD, 5 C.DMG for damage dealers); `mains` per slot, e.g.
  `((Slot.RING, (Stat.ATK,)), (Slot.AMULET, (Stat.CD,)), (Slot.BANNER, (Stat.ATK, Stat.RES)))`.

Always write the reason: why the formulas are wrong for this champion, so the entry can be
checked again after a rework. Form numbers are 1-based, as the report shows them.

## 5. Check

- Re-run the report: the form shows `overridden` and the intended type.
- `uv run --group dev ruff check optimiser && uv run --project ~/repo/python-style python-style optimiser`.
- The web UI reloads by itself; Accessories → Weights lists the faction types, and the
  Clean up tab's counts show what the change moved. Tell the user what moved.
