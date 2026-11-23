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

## Damage

Read from the 11.95.0 code (disassembly of `DamageProcessor`, `DamageCalculator`,
`DamageContext`, `ShareDamageProcessor`, `ReflectDamageProcessor` and the multiplier
processors; the effects themselves from the static data's `SkillTypes` and
`EffectData.EffectTypes`). The DEF multiplier and the crit/ignore-DEF terms are what
`optimiser/damage.py` uses. `optimiser/hit.py` is the reference model of a hit, and what it
covers is **checked bit for bit against the game's own code**, run in an emulator (below,
"The reference model"); marked ✓ here. That's the code, with inputs we build: not a battle in
the game. What isn't marked was read, not run.

### How a hit is put together

A hit is an effect of kind `Damage` (6000) run by `DamageProcessor.Process`. Everything else
that changes it (skills' passives, sets, masteries, relics, buffs and debuffs) is an effect that
names a **phase** of the hit and the **effect kinds** it reacts to (`Relation.EffectKindIds`,
`Relation.Phases`, plus its `Condition`), and runs when the hit reaches that phase. Which
processor runs an effect kind is `EffectProcessorContainer..ctor`'s table.

The hit's state is a `DamageContext`: the multiplier (`_multiplierValue`, never below 0), the
DEF modifier (`_defenceModifier`, clamped to [−1, 0]: DEF can be ignored, never raised), the
hit-type chances, the crit-damage modifier, `IsBlocked`, and two results:
`CalculatedDamage` (set once) and `DealtDamage` (a copy that later steps change).

The steps, in the order `Process` runs them (phase ids from `BattlePhaseId`):

| # | Step (phase id) | What happens | Hooked by |
|---|---|---|---|
| 1 | context | multiplier = the skill's `MultiplierFormula` (a placed status's custom multiplier if it has one); a negative one logs an error and the hit does nothing. DEF modifier ✓ = `DamageParams.DefenceModifier` (or the status's `IgnoreDefValue`) clamped to [−1, 0], then, on a `Damage` hit at an enemy, minus the attacker's IgnoreDefence stat, clamped again (so a skill's positive modifier doesn't offset the stat). Crit chance ✓ = C.RATE + `DamageParams.IncreaseCriticalHitChance`; glancing and crushing chances 0. Counterattack modifier from the skill's `SkillModifiers`. | |
| 2 | AfterDamageContextCreated (55) | | `ChangeCritChance` (adds to crit chance) |
| 3 | BlockDamageProcessing (54) | Block Damage: the multiplier goes to 0 (kept as `AbsorbedByBlockDamage`), `IsBlocked` set; a bomb's stored value is zeroed too | Block Damage buff (also on glancing hits) |
| 4 | hit type (`SetHitModifiers`) | affinity and hit type, below | |
| 5 | AfterHitTypeCalculated (57) | | |
| 6 | BeforeDamageCalculated (50) | the multiplier's modifiers | `ChangeDamageMultiplier` (sets, masteries, passives), Weaken/Strengthen/Rage/Inspiration, `ChangeDefenceModifier` (set and skill ignore DEF), `ChangeEffectCritDamage`, Share Damage buffs, Bulwark, Selfless Defender |
| 7 | IgnoreDefenceModifierProcessing (240) | | `IgnoreDefenceModifier`: target-side passives scaling the attacker's ignore (`k*relationDamageDefenceModifier`) |
| 8 | CrabShellProcessing (160) | | |
| 9 | calculate | `CalculatedDamage` = the formula below; `DealtDamage` = a copy | |
| 10 | AfterDamageCalculated (51) | | `ChangeCalculatedDamage` on dealt: HP caps (`−(CALCULATED_DMG−0.1*HP)`), anti-Stone Skin sets |
| 11 | NewbieDefenceProcessing (341) | | |
| 12 | absorption: Cocoon (59), On Guard (201), Stone Skin (200) | | |
| 13 | AfterFinalDamageCalculated (350) | | `ChangeCalculatedDamage`: Owein's −25/50 %, Full Synchronization |
| 14 | BeforeDamageDealt (52) | shields absorb from dealt | Shield, Magma Shield, Bone Shield, Hit Counter Shield, Crit Shield |
| 15 | Golden Armor (202), Digestion (220) | | |
| 16 | cap | dealt = min(dealt, max(cap, 0)) if the effect has a `ValueCapExpression` | |
| 17 | HP | Chimera competition points, then HP − dealt (`BattleHero.DecreaseHealth`) | |
| 18 | UnkillableProcessing (58) | a dying target is kept alive (`UnkillableProcessor.TrySaveHero`) | Unkillable (status and passive) |
| 19 | DelayedLetalyDamageProcessing (342), HealthReduced (63) | then Sleep is removed; Thunder counter (290), challenge progress (330) | |
| 20 | AfterDamageDealt (53) | | reflects, Mark (Hex: 10 % / 2 % on AoE of DEALT_DMG), Mirror Damage, on-hit passives, Owein's reflect |

A blocked hit's multiplier modifiers do nothing: `ChangeDamageMultiplier`,
`StatusChangeDamageMultiplier`, `ChangeCritChance` and `ChangeEffectCritDamage` all return
early on `IsBlocked`.

What a hooked effect's formula reads (`RelatedEffectResultParamsBuilder.Build` binds them):

- `DMG_MUL`: the hit's **current** multiplier (`RelatedEffectsDamageMultiplier`), not the
  base, whatever its description says. So it includes every step 6 effect that ran first.
- `CALCULATED_DMG`: `CalculatedDamage`, set at step 9 and never changed afterwards.
- `DEALT_DMG`: `DealtDamage` less overkill (`ActualValue` = value − `ExcessiveValue`), after
  steps 10–16 have changed it. Whether shields' absorption comes off it was not traced.
- `relationDamageDefenceModifier`: the DEF modifier (−1 = all DEF ignored).

### Affinity and hit type (`SetHitModifiers`, `CalculateHitType`)

- Fixed damage (`DamageParams.IsFixed`) is always neutral and Normal.
- Affinity: the DamageParams' preset, else from both champions' current form element
  (`ElementExtension.GetElementRelation`).
- Hit type ✓: the DamageParams' preset, else Glancing if the target is under Poison Cloud and
  not Burning (a hit from the other side: another `OwnerUserId`) or the attacker is Enfeebled
  (neither if the hit ignores that effect). Else, if any chance is set, **one** roll
  (`NextFixed`: in [0, 1)), checked against glancing, then crit, then crushing; a chance (with
  its affinity bonus) at or below `Fixed.Epsilon` never lands, one at 1 or more always does,
  else the roll must be below it:
  - glancing chance: 0, +35 % when weak (`GlancingHitChance`);
  - crit chance: C.RATE (+ skill extra, + `ChangeCritChance`), +15 % when strong
    (`CriticalHitChanceAdvantage`);
  - crushing chance: 0, +50 % when strong (`CrushingHitChance`).

  So a glancing hit can't crit, and a strong hit's crushing chance is 50 % of what didn't crit.

### The calculation (`DamageCalculator.Calculate`) ✓

```
damage = multiplier
       × (1 + skill bonus)    the skill's DamageModifier (books); Damage kind only, not on oneself
       × (1 + affinity)       −0.2 when weak (ElementDisadvantageCoef), else 0
       × (1 + hit bonus)      crit: C.DMG + crit modifier; crushing +0.3; glancing −0.3; normal 0
       × (1 + counterattack)  the skill's CounterattackModifier (counterattacks: −0.25)
       × (1 + stat modifier)  DamageModifierFromStats; Damage kind only
       × DEF multiplier       left out when useDamageReduction is false (reflects)
       × status reductions
       × roll                 n/100, n uniform in 90…109 (mean 0.995); not for fixed damage
```

- **Crit**: the dealer's C.DMG stat plus the context's `CriticalDamageModifier`
  (`ChangeEffectCritDamage` adds to it). The dealer is the effect's producer, or the original
  hit's when `ShareDamageParams.CritFromOriginalProducer` is set. Increase C.DMG buffs are a
  stat change (+0.15 C.DMG). There's no cap anywhere.
- **DEF multiplier** (`DamageReductionByDefence`): `1 − 0.85 × (1 − e^(−effDEF/1500))`,
  effDEF = (DEF − ignored Increase DEF) × (1 + DEF modifier). The game computes it as
  `e^(−2·effDEF/3000)`. If the hit ignores `StatusIncreaseDefence`, each of the target's Increase
  DEF buffs' DEF comes off first. The DEF modifier is the sum of the skill's own (negative =
  ignore), the attacker's IgnoreDefence stat and every `ChangeDefenceModifier` (they **add**),
  clamped to [−1, 0] at each step.
- **Status reductions** (`DamageReductionByStatusEffects`): (1 − 0.25 if Frozen − 0.075 if Veil
  on an AoE hit − 0.15 if Perfect Veil on an AoE hit) × the target's Stone Skin factor × its
  Petrification factor × the Newbie Defence factor. Stone Skin and Petrification factors come
  from their params by the hit's kind (Bomb, AoE DoT, other). Each is skipped if the hit's
  `IgnoreStatusEffectReductionList` or ignored effects name it. Weaken and Strengthen are
  **not** here: they're step 6 multipliers.
- **Stat modifier** (`DamageModifierFromStats`, `BattleHero.DamageStats`): a sum of the
  attacker's dealt and the target's taken substats. In PvP (Arena, Tag Team Arena, Live Arena,
  Siege: `IsBattleWithPlayer`) it's dealt PvP + taken PvP. Otherwise it's dealt PvE + taken PvE,
  + dealt/taken Dungeons in a Dungeon, + taken Boss when the attacker is a boss, + dealt Boss
  when the target is one.
- **Roll**: `FixedRandom.Next(90, 110) / 100`, upper bound exclusive (`FixedRandom` is
  xorshift128 over four uint32s, `Next()` its value's low 31 bits). It is skipped for fixed
  damage and when `BattleState.IgnoreRandomDamage` is set.
- **Fixed arithmetic** (`Plarium.Common.Numerics.Fixed`, Q32.32): products floor, quotients
  round half up (on the magnitude), sums saturate, `(Fixed)double` truncates, `FixedMath.Exp` is
  `(Fixed)Math.Exp((double)x)`. `optimiser/fixed.py`.

The game's constants (static `GameplayData`): ElementDisadvantageCoef −0.2, CrushingHitCoef 0.3,
GlancingHitCoef −0.3, CriticalHitChanceAdvantage 0.15, CrushingHitChance 0.5, GlancingHitChance
0.35, CounterattackModifier −0.25, CriticalHealCoef 0.5, ShieldCapValue 1,000,000.

### How the modifiers combine

- `ChangeDamageMultiplier`: multiplier += its formula, evaluated when that effect runs. Formulas
  are nearly all `k*DMG_MUL`, and `DMG_MUL` is the current multiplier, so **separate effects
  compound**: (1 + a)(1 + b). Within one effect the counts are linear: Zeal's
  `DMG_MUL*HP_PERC/0.25*0.03*sameSkillCount` gives +12 % per set at full HP, Fury's tiers give
  10/25/50 %. So Zeal 3 + Fury at full HP is ×1.36 × 1.10 = 1.496, where `optimiser/damage.py`
  adds them (1.46). ✓ for the processor: run twice with `k*DMG_MUL` formulas, 1000 → 1360 →
  1496 (`test_zeal_and_fury_compound`), granted the phase runs its effects one after another,
  as each `Process` call does. The order of effects within a phase wasn't traced; it only
  matters for formulas that set an absolute value (the Chimera's `−(DMG_MUL−k)`: the multiplier
  becomes k).
- Weaken (×1.25 / ×1.15), Strengthen (×0.75 / ×0.85), Rage, Inspiration
  (`StatusChangeDamageMultiplier`) ✓: multiplier ×= formula, or a bomb's stored value if the hit
  is a bomb (they react to `Damage`, `TimeBomb` and `Infest`, not DoTs).
- `ChangeDefenceModifier` ✓ and `IgnoreDefenceModifier`: added to the DEF modifier, clamped to
  [−1, 0]. Set ignore DEF is this: Lethal/Savage share skill 100010 (25 %, once), Cruel 5 % ×
  sets, Slayer AoE only, all multiples of 5 %.
- `ChangeCritChance` and `ChangeEffectCritDamage`: added.
- `ChangeCalculatedDamage` ✓: added to `DealtDamage` (never below 0), unless the hit says its
  damage can't be changed. `CALCULATED_DMG` keeps the pre-change value, so Owein's reflect
  reads what was calculated.

The sets' damage bonuses are exported as `damage_bonus` at full HP. Zeal scales with the
wearer's HP, not the target's. No set adds damage by target HP (Slayer 9's extra hit is only
capped by it). Feral and Protection 9 (per buff/debuff on the target) are left out.

Skill formulas (`MultiplierFormula`) are mostly `k*STAT`. Anything using target or battle
state (`TRG_HP`, counts) isn't supported.

### Kinds that aren't hits

A hook reacts only to the kinds it lists, and most list `Damage` only. Reflected damage
(`ReflectDamage`, `PassiveReflectDamage`), shared damage (`ShareDamage`, `PassiveShareDamage`),
DoTs (`ContinuousDamage`) and bombs (`TimeBomb`) are other kinds. They run their own processors
and aren't seen by `Damage`-kind hooks (Weaken lists bombs, not DoTs; reflects don't reflect
reflects).

- **Reflected damage** (`ReflectDamageProcessor`: a `DamageProcessor` whose `CalculateDamage`
  turns `useDamageReduction` off; `MagmaShieldReflectDamageProcessor` extends it). It runs all
  20 steps. It's fixed (neutral, Normal, no roll) and skips the target's DEF, but the target's
  status reductions, Block Damage, shields and Unkillable still apply. Sources:
  - Reflect Damage buffs: 15 % / 30 % of `DEALT_DMG`, not processed the turn they're placed.
  - Passive reflects: Owein 25 % / 50 % of `CALCULATED_DMG`, Construct of Siroth 50 % of
    `DEALT_DMG`.
- **Shared damage** (`ShareDamageProcessor.ShareDamage`; Share Damage buffs 50 % / 25 %, Bulwark
  5 %). At step 6 of the hit on the ally, that hit's multiplier loses `TargetDamageCutPerc`. The
  shared part is a new context of that cut, built from the original hit: its DEF modifier unless
  `ShareDamageParams.DefenceModifier` is set, and its hit type and affinity. It is then
  × `TransferedDamagePerc` × the receiver's DEF multiplier × the receiver's status reductions.
  - No roll; no skill bonus or stat modifier (both are `Damage`-kind only).
  - The crit bonus uses the share effect's producer's C.DMG unless `CritFromOriginalProducer` is
    set (read, not checked).
  - It runs BlockDamageProcessing (54), AfterSharedDamageCalculated (340), the special
    absorptions, its own shield step, Golden Armor/Digestion, HP, Unkillable (58) and
    HealthReduced (63). Nothing at 51, 350 or 53: no reductions there, no reflect, no on-hit
    passives.
- **Selfless Defender** (500251) isn't a share. Its −20 % is a `ChangeDamageMultiplier` on the
  ally's hit, and the holder takes a separate fixed `Damage` effect of `0.2*DMG_MUL/0.8` (the
  original 20 %) at AfterDamageDealt. It counts the holder's DEF, with no crit and no roll.
- **DoTs and bombs**: fixed damage. Poison is 5 % / 2.5 % of target MAX HP and HP Burn 3 %, both
  with DEF modifier −1 (all DEF ignored). A bomb is 5 × ATK, fixed and against DEF. Their own
  processors (`ContiniousDamageProcessor`, `TimeBombProcessor`) were not read beyond that.

**Example: Owein Winterflame and Bulwark.** Owein's passive (107804) is four effects on
`Damage`-kind hits from enemies:
- `ChangeCalculatedDamage` at 350: −0.25 × `CALCULATED_DMG`, or −0.5 under Shield or Magma
  Shield.
- `PassiveReflectDamage` at 53: 0.25 / 0.5 × `CALCULATED_DMG` to all enemies. That is the same
  amount the reduction took off.

So:
- **Bulwark on Owein**: the 5 % of his allies' hits that he takes is shared damage. His
  reduction doesn't apply to it and he reflects nothing from it, though his shields absorb it.
- **Bulwark on a teammate**: the cut comes at step 6, before step 9, so Owein's
  `CALCULATED_DMG`, and with it both his reduction and his reflect, are 5 % smaller.

### The reference model, and testing it against the game's code

`optimiser/hit.py` is a hit as `DamageCalculator` and `DamageContext` compute it, in the game's
`Fixed` arithmetic (`optimiser/fixed.py`): the context's DEF modifier and crit chance, the hit
type and its roll, `CalculateDamage`'s factors, the substats, the DEF multiplier, the Freeze
and Veil reductions, the roll, and what the multiplier, DEF-modifier and dealt-damage hooks do.
The solver doesn't use it (`optimiser/damage.py` is its linear stand-in).

`just test-game` (tests/test_game_code.py) checks it against the game's own machine code. Each
case is built twice, as the model's inputs and as the game's objects, and the game's method
runs in an emulator (`tools/game_emulator.py`: GameAssembly.dll loaded into Unicorn, objects laid
out from the dump's field offsets, `tools/dump_types.py`). Results must match bit for bit, over
a thousand seeded random cases per method (~40 s in all). The game itself doesn't run: only the methods
called and what they call. libil2cpp's runtime is stood in for by hooks (metadata, class init
and static constructors, allocation, array initialisers), found by where known methods call
them, so a game update needs only `just update` (its dump) and maybe a fix where code moved.
The rest is answered in Python only where the emulator can't run it, never in the code under
test: battle pools' result objects, LINQ's generic `Contains`, the influenced-effects HashSet;
a hooked effect's compiled formula is a few x86 instructions calling the game's own variable
getter (`k*DMG_MUL`), and a processor runs up to the setter that changes the hit (what follows
is its action results' bookkeeping). The test needs the dump of the installed GameAssembly.dll
(its `source.sha256`), and `uv`'s `emulate` group (unicorn, pefile, capstone).

What the emulator found that reading had missed: the context's DEF modifier is clamped before
the IgnoreDefence stat comes off as well as after; Poison Cloud only glances hits from the
other side, and not while the target is Burning.

### Not traced

- How shields absorb (`AbsorbDamageProcessor`), and whether `DEALT_DMG` at step 20 is net of
  them.
- Unkillable beyond "keeps a dying target alive".
- The order of effects within one phase.
- The DoT and bomb processors' overrides.
- The Newbie Defence skip that a static setting enables.

## Resist (read from `EffectManager.IsResisted` / `TryResist`)

- `optimiser/accuracy.py`. d = target RES − caster ACC (`ApplyContext.get_Accuracy/
  get_Resistance`: stat + per-application modifier, at least 0; RES × (1 − the skill's
  `IgnoreResistanceModifier`) first). Resist chance: d < 30: 0.03 + 0.27 e^(6 (d/100 − 0.3));
  d ≥ 30: 0.30 + 0.67 (1 − e^(−3 (d/100 − 0.3))); resisted when a random Fixed ≤ it. So 3 %
  floor, 97 % cap, 7.5 % at ACC = RES; no breakpoint, the floor is only approached. Rolled
  apart from the skill's own chance. Within 0.1 points: ACC ≥ RES + 64 (floor), RES ≥ ACC +
  247 (cap).
- ✓ against the game's code (`just test-game`, `test_resist_threshold`): computed in `Fixed`,
  as `IsResisted` does, so the floor is `(Fixed)0.03` = 0.0299999998 and the cap a hair under
  97 %. The test finds the game's threshold by binary search on `IsResisted`, with xorshift
  states built (run backwards) to give each roll.
- Rates as goals and minimums (`accuracy.Lands`, `accuracy.Resists`; the champion page's
  "Debuffs land" / "Resist debuffs" rows, Team gear's rank choices): the curve rises steadily
  with the stat, so each rate is exactly a stat threshold. "Lands at least x %" becomes an
  ACC minimum, "resists at least y %" a RES minimum (`accuracy_for_resisted`,
  `resistance_for_resisting`: the least whole stat, by binary search). Ranked, a rate is its
  stat capped at the floor or cap (`most_useful`), and held within the slack of its best
  *rate*: the least stat for that rate. So the solver stays linear. Slack in rate terms is
  worth more stat near the floor and cap: 1 % of a 97 % land rate is ~120 ACC at 150 RES.

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
