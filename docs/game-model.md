# How the game computes it

Moved out of CLAUDE.md on 2026-11-21; the code map stays there. Each number here was read off the
game's code or data and checked against the game (Anaxia's in-game stats, the oracle's tables).

## Stat model (verified exact against the game)

stat = base + Great Hall + arena + awakening + empower + masteries + relics + gear, with
percentages applying to **base** stats except crit (C.RATE/C.DMG percentages add).
Anaxia's in-game stats matched exactly.

- **Base:** static data holds unscaled stats with HP ÷ 15 and crit in %. Rank/level scaling
  is in code (`HeroExtensions.GetBaseStats` → `BattleStats.BuildFromBase` → `CalcValue`):
  HP/ATK/DEF = `Round(base × a × b^((L−1)/(10g−1)))`, (a, b) per rank from the static
  `BattleStats.Multipliers` (filled from metadata; 1.0 at 1★ L1, 11.01 at 6★ L60), in Q32.32
  `Fixed` (doubles truncate, products floor, round half to even); HP then × 15, crit ÷ 100.
  `optimiser/levels.py` reproduces it; no oracle data is needed.
- **Ascension** (0–6) is the last digit of `TypeId`; each ascended type has its own base stats.
  **Awakening** (`AwakenedGrade`, "double ascend") is a separate thing: flat bonuses per rarity,
  cumulative per star (`bonuses.json` `awakening`).
- **Empower:** cumulative per level; Epic has its own table, Legendary/Mythical share one
  (checked against `CalcEmpowerBonus`).
- **Great Hall:** per affinity and stat level from the snapshot's `great_hall` (values per
  level, not cumulative). **Arena:** its `arena_league` (Gold V +22% HP/ATK/DEF).
- **Masteries:** 13 stat masteries; Lore of Steel (500343) multiplies set stat bonuses by
  1.15 (the game lists that extra under masteries).
- **Relics:** a type's stats unlock at levels 0/9/15; a stat's value is
  `values[stat][level - unlock level]`. Stones add skills only.
- **Gear:** substat value + glyph (`Enhancement`); artifact ascension adds `AscendBonus`.
  Main stat by slot/rank/level is `ArtifactData.PrimaryBonusInfos`, ascension bonus by
  slot/rank/ascend level `AscendBonusInfos` (ranks 4-6); rarity changes neither.
  Glyphs are `BlackMarketData` items' `PowerUpData` (stat, rank, rarity, min/max roll): ranks
  1–5 Uncommon only, 6 in Uncommon–Legendary; substats only, no C.RATE/C.DMG glyphs.
  Accessories may be faction-locked. Sets: fixed (per N pieces) or variable (cumulative total
  at each piece count, accessories count).
- Pieces carry the game's set id. HH named sets differently (HH `AttackPowerAndIgnoreDefence`
  = Cruel). Two placeholder sets (55, 56) are unreleased prototypes, hidden.

## Damage (read from `SharedModel.Battle.Core.DamageCalculator` disassembly)

- `damage = formula × (1 + books) × (1 + hit bonus) × other (1 + x) factors × DEF mult ×
  status-effect reductions × random roll`.
- DEF multiplier = `1 − 0.85 × (1 − e^(−effDEF/1500))`; effDEF = DEF × (1 + defenceModifier);
  defenceModifier = skill's `DefenceModifier` − sets' ignore DEF (they **add**).
- Crit hit bonus = C.DMG + skill crit extra, **no cap** anywhere. C.RATE is a probability.
- Sets' damage bonus (`ChangeDamageMultiplier` passives on the owner's own hits, exported as
  `damage_bonus` at full HP): Zeal +12 % per set (`sameSkillCount`), capped at 36 %; Fury +10 %
  once (more below 75 % HP, not modelled). They add, × (1 + bonus). Zeal scales with the
  wearer's HP, not the target's; no set adds damage by target HP (Slayer 9's extra hit is only
  capped by it). Feral/Protection 9 (per buff/debuff on the target) are left out.
- Set ignore DEF comes from `ChangeDefenceModifier` passives on set skills: Lethal/Savage share
  skill 100010 (25 %, once); Cruel 5 % × sets; Slayer AoE only; values are multiples of 5 %.
- Skill formulas (`MultiplierFormula`) are mostly `k*STAT`; anything using target/battle
  state (`TRG_HP`, counts) isn't supported.
- `DamageModifierFromStats` applies dealt-damage substats (PvP/boss/dungeon), not modelled yet.

## Resist (read from `EffectManager.IsResisted` / `TryResist`)

- `optimiser/accuracy.py`. d = target RES − caster ACC (`ApplyContext.get_Accuracy/
  get_Resistance`: stat + per-application modifier, at least 0; RES × (1 − the skill's
  `IgnoreResistanceModifier`) first). Resist chance: d < 30: 0.03 + 0.27 e^(6 (d/100 − 0.3));
  d ≥ 30: 0.30 + 0.67 (1 − e^(−3 (d/100 − 0.3))); resisted when a random Fixed ≤ it. So 3 %
  floor, 97 % cap, 7.5 % at ACC = RES; no breakpoint, the floor is only approached. Rolled
  apart from the skill's own chance. Within 0.1 points: ACC ≥ RES + 64 (floor), RES ≥ ACC +
  247 (cap).

## Solver

MILP in HiGHS (`highspy`). A binary per wearable piece (faction, open slot: `slot_unlocked`, the game's
`RequiredHeroGradeByKindId` Ring 4 / Amulet 5 / Banner 6 stars, Amulet and Banner also ascended that
far; `GearFilter`, `above_level` filter),
one per armour slot, ≤ 1 per accessory slot; set bonuses exact via piece-count variables
tied with equalities. Ranking is lexicographic: maximise each goal, then hold it within
`slack` (relative; for damage, applied to damage not its log). Builds after the first exclude
earlier ones with no-good cuts. Dominance pruning drops pieces that ≥ `builds` others in the
same slot/set/faction match or beat on every stat the request uses.

Damage is ranked by its log: tangent lines under log(formula) and log(1 + C.DMG) (20 each,
over the reachable range: fewer, tighter tangents were several times faster); the DEF term
(convex in ignore DEF) is exact with a binary per 5 % step, the steps stopping at the most any
build ignores (`most_ignore`, a small side solve): the relaxation takes the chord to the top
step, and topping out at every source summed (DEF multiplier 1) left the gap ~5x wider.
Tangent rows go through one variable per term (`log_under_tangents`), not a term per piece.
HiGHS has no MIQP and damage is a non-convex product anyway, hence the log form. A damage
solve with four stat minimums takes ~15 s per build; the slack left in the bound is fractional
set counts (parts of Merciless and Lethal both claiming their ignore).

## Raider oracle (game-code calls)

No longer needed for base stats (`optimiser/levels.py`); kept for checking formulas against
the running game (`just check-levels` compares with its 6★ L60 table).

`~/repo/raider`: a Rust DLL injected into Raid.exe that calls IL2CPP methods. **Only ever inject
into the throwaway account's prefix `~/tmp/inject-test`, never the user's main install.**
The payload dumps hero stats (`/tmp/raider-stats.json`) and answers
`/tmp/raider-oracle-request.txt` ("type grade level form [empower]") with in-memory heroes
never added to the account. Look offsets up by field name (they move between game versions),
pass value types to `il2cpp_runtime_invoke` by pointer (`Nullable<int>` as
{bool hasValue; int value}), unbox struct enumerators for `this`, and release the
`AppModel.ReadUser` guard.

Method bodies (`just dump`, described in CLAUDE.md, says where the dump is and when it's skipped):
disassemble `GameAssembly.dll` at the dump's RVAs (capstone), labelling calls from `script.json`.
Static array initialisers (`<PrivateImplementationDetails>` fields) show their data's offset in
`global-metadata.dat` as `/*Metadata offset 0x…*/` in `dump.cs`.

## Assets

Portraits are named by type id with ascension 0 (`9990`); enemies' (bosses, Hydra heads, from
`HeroAvatars_Bosses`/`HeroAvatarsHydra`) by full type id, via their type's `avatar`. Piece art `<set id>_<slot>`, set
icons by set id. Affinity icons by lower-case affinity, faction banners by faction key (`account.faction_name`: the game's internal name, but
Samurai → Shadowkin, Olympians → Argonites, which the game's tables, stage conditions and
crypts still use; champions, pieces and relics carry the key; `faction_label` is what's
shown (views carry it: `PieceView.faction_label`, the team views' factions): "Dark Elves", "Lizardmen"), stars `yellow`/`purple`/`red` (plain/ascended/awakened). Fusion
portraits are in `FuseAvatarsLocal`. Set accessories use the set's generic art even when faction-locked; only
set-less accessories use `<faction>_<slot>`. Old sprite names mapped by the user: Berserker = Crit
Damage, Healing = Regeneration, Rage = Killstroke, Stalwart2 = Defiant, Taunting = Provoke,
Warrior = Cruel. Accessory-only sets have no icon. The images are Plarium's art: keep local.
