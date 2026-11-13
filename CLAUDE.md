# raid-optimiser

An experimental, personal gear optimiser for Raid: Shadow Legends: cruder and faster than
HellHades' (HH) optimiser rather than a copy of it. The user pays for HH and keeps using it;
**don't use or port HH's source or algorithms**. Its data models are used only to decode
its upload. Game tables come from the game's own data.

## Layout

- `data/` (gitignored): everything that isn't code. `captures/` (the capture), `game/` (the
  game's tables), `state/` (the store), `cache/` (the decoder's hero-type list);
  `optimiser/paths.py` names them. `schema/` (tracked) stays at the top.
- `capture/hh_capture.py` + `run-proxy.sh`: mitmproxy tees the HH extractor's upload
  (`POST /api/Account/v2`, MessagePack + LZ4Block `RaidData`). `decoder/` (C#, references HH's
  DLLs) writes `data/captures/latest/{account,champions,artifacts,set_ids}.json`.
- In game: the same addon serves `POST 127.0.0.1:8081/equip` (`{"hero_id", "artifact_ids"}`,
  `EquipArtifacts`) and `/preview` (`{"account_id", "hero_id", "artifact_ids"}`, `PreviewBuild`,
  the game's build preview: nothing changes, no sync follows). It injects the SignalR
  invocation into the extractor's `/reader` hub WebSocket, as if HH's server sent it, then
  waits for (and swallows) the extractor's `HelperRequestResult`. `account_id` is the
  capture's `UserId`. `webui/extractor.py` is the client; each build has both buttons.
  `/sell` (`{"artifact_ids"}`, `SellArtifacts(int[])`) only selects the pieces in the game's
  sell screen; the user confirms the sale in game. Only the accessories page sends it, and
  only pieces its current plan sells (`forms.parse_sell`).
- `update-static.sh`: decodes the game's cached static data
  (`LocalLow/Plarium/Raid_ Shadow Legends/static-data/<ver>/<hash>`, MessagePack
  Lz4BlockArray, string keys) via `tools/static_export.py` and `schema/schema.json` (from an
  IL2CPP dump, `tools/gen_schema.py`) into `data/game/{sets,hero_types,bonuses,skills,glyphs,gear,enemies,effect_sources}.json`.
- `optimiser/levels.py`: base stats at any rank/level, computed as the game does (below);
  `tools/check_levels.py` checks its table is still in the game's metadata (`update-static.sh`)
  and, given a raider oracle table, compares results. `tools/oracle_request.py` /
  `tools/oracle_import.py` drive the oracle (below), now for checking only.
- `optimiser/enemies.py`: the enemy store (`data/game/enemies.json`, types' base stats from
  `hero_types.json`): every stage's formations, team restrictions (every champion must match;
  `MinCount`/`MaxCount` are the team size), stat modifiers (stage-wide and per slot: a relative
  `value` multiplies base by 1 + value, checked against the Chimera's listed HP; slot modifiers
  give UNM clan boss its 190 SPD / 225 RES / 225 ACC), boss kinds, enemy skills, clan boss tiers,
  the Chimera (forms in type order Ultimate/Ram/Lion/Snake, form sequence, trials with targets
  from their hidden `StartChallenge` skills) and per-area shield caps. `enemy_stats` is stats as
  a battle starts (no in-battle passives). `just enemies` (`optimiser/enemy_report.py`) prints it.
  The co-op event world boss (Tainted Demon Lord) is area `CooperationEventWorldBoss`.
- Chimera trials (`/chimera`, `optimiser/chimera/`): one team of five that clears a whole
  column (Wing/Tail/Paw: where this rotation's mythical materials are; the user picks, the
  capture doesn't say) in all three animal forms, Easy→Normal→Hard, in one UNM fight (rewards
  only count for trials cleared in the same fight). Judged on what champions can place and do,
  not damage (targets are shown, not checked), nor turn order, nor ACC against the RES.
  - `tags`: `Tag` (debuff/buff status kind with strengths merged by `status_kind`, a skill
    effect from the curated `EFFECT_LABELS`, or a `Mechanic`); immunities: `BOSS_IMMUNE` minus
    `FORM_ALLOWS` (Ram takes Fear, Snake Block Active Skills; `NEVER_LANDS`, `only_in`).
  - `trials`: `trial_needs` (a `match` per trial; counts from the trial's target or `rules`),
    checked against the trial's own status list (`check_needs`; the page warns on a
    mismatch). The `DEBUFF_COUNT>=` trials (Lion Wing Easy, Lion Paw Normal, Snake Wing Hard)
    count instances (`Distinct.instances`): any Poison source meets them, given speed.
    `Goals` (trials' needs + wanted extras) → `Requirement`s (a need and its form).
  - `kits`: a champion's `Kit` from `skills.json` (`placements`, `books`, `effect_kinds`,
    `target_hp_damage`), all forms of a mythical, each tag's best `Rating` = uptime (turns ÷
    cooldown less cooldown books; passives and A1s every turn; instant: 1 ÷ cooldown) ×
    reliability (chance + chance books, × `CONDITIONAL` if gated) × reach (`REACH_TEAM`/`ALLY`/
    `SELF`; debuffs, mechanics and enemy-side effects in full), × `OTHER_FORM` for a
    mythical's other form. Own skill levels count (`Cast`). Each placement's `on_boss`
    (`static_export.on_boss`: its effect and target conditions read three-valued with the
    boss atoms, `BOSS_FACTS`, true) drops what never lands on a boss (Lamasu's True Fear goes
    to non-bosses; bosses get Decrease SPD), and only what depends on more is `CONDITIONAL`.
  - `gear`: `effect_sources.json` (each set's set skills, each relic type's skills and faction
    skills, capture faction names) → `Gear` options (every set, relics the account owns,
    `Account.relic_types`), rated like skills. Allowed ones (`gear=<Gear.key>`, `gear_set`
    marks the list as sent; default `DEFAULT_GEAR`, Toxic) and team-wide assumptions make needs
    `Given` (`with_gear`); faction relic skills (Bloatshield Totem's Demonspawn reflect) and
    per-champion assumptions (`assume=<champion id>@<tag key>`) join those kits (`equip`).
    Gear doesn't count toward "N different" needs.
  - `cover`: who covers what (`Lineup`), the members a team needs (`core_of`), the score: a
    team's sources of a tag combine as 1 − Π(1 − s); a need scores its best tag (a count: its
    best N's mean; `Given`: the gear's rating); `team_score` is the mean over `Goals`'
    requirements and ranks the options (`ranking`: then fewest champions, then strength).
  - `search`: `every_team` lists every minimal team clearing all nine and bringing the extras
    (branch on the unmet need fewest champions bring; "any champion" fills the rest), within
    `SEARCH_BUDGET` (20,000 teams or 1 s: with nothing pinned there are hundreds of thousands,
    mostly from the "N different" trials); if none clears all nine, `partial_teams` (HiGHS)
    gives the best partial ones.
  - `plan`: `check_lineup` (the slots alone) and `fill_lineup`, from a `Brief` (column,
    wanted, loadout).
  - Page (`webui/service/chimera.py`; `forms.parse_chimera` is its boundary, `ChimeraRequest`
    with `fill: Fill | None`): rotation, slots (`slot` ×5, "Name, 6★ L60 #id" from a datalist,
    or part of a name), "Also bring" (`want=<Tag.key>`, from `wantable`), gear, relics &
    assumptions, Run (3 options, 9 more per "show more", at most 300; `option` picks the one
    the grid shows; "Use this team" puts it in the slots), then the 3×3 board. State is all in
    the URL. Icons: `statuses/` (StatusEffectIcons, by status kind; `service.chimera.icon_name`
    maps ours, e.g. DecreaseDefence → StatusReduceDefence) and `chimera/<Form>_<Level>`
    (ChimeraChallengeIcons), from `tools/extract_assets.py`.
- `just dump`: Il2CppDumper over the installed game into `data/dump/<game version>`
  (`dump.cs`, `script.json`): `just schema`'s input and the source of RVAs to disassemble.
- `tools/extract_assets.py`: portraits, set icons and piece art from the game's Unity bundles
  (UnityPy) into `webui/static/assets/`.
- `optimiser/`: the model and solver (`account`, `stats`, `damage`, `solve`, `assume`, `glyphs`,
  `labels`), `paths` (where the data lives) and `settings` (the store's rows as the model's
  types: the only model module besides `store` that touches the file).
- `optimiser/store.py`: user state the capture doesn't hold, in SQLite at `data/state/optimiser.sqlite`
  (stdlib `sqlite3`): champion locks 1–5, set on the champion list. A solve's gear pool
  (`AnyGear | UpToLock(level) | Unequipped`) decides whose worn gear it may take; the
  champion's own gear is always allowed.
  Also what solves assume (account-wide, `/assumptions` page; `optimiser/assume.py`): flags for
  the champion at their rank's top level, gear at +16 (main stat only) and ascended gear fully
  ascended (`planned_*` fields; `data/game/gear.json` tables, checked exact against every piece),
  and glyphs to assume (a grade per kind): `optimiser/glyphs.py` gives solves a copy of the account whose substats of those kinds carry the grade's top roll
  (`StatLine.planned_glyph`), capped below 6* at the best glyph of the piece's rank, where it
  beats the real glyph; current stats use the real gear. Only stats the request wants more of
  are glyphed (`solve.directions` > 0: minimums, ranked stats, the damage skill's stats + C.DMG).
  Also each champion's run history: the submitted form and the outcome view
  (`dataclasses.asdict` JSON, rebuilt by `service.runs.revive`; a run whose shape no longer fits
  shows only its inputs). The page opens on the latest run; nothing is kept in the browser.
- Accessories (`/accessories`, tabs in the workflow's order: Swaps · Roll · Rework · Clean up,
  then Weights; `optimiser/accessories/`, which doesn't use the solver). Only unequipped gear takes
  inventory space (2200 for accessories); overflow waits in the mailbox (the capture's
  `InboxItems` "Overflow" artifacts, `Account.mailbox`).
  - `roles.py`: champion types (ATK/HP/DEF damage, bomber/poisoner, support: per-stat weights,
    stored in `type_weights`, and the main stats that suit them) and set roles (Damage, Hybrid,
    Support, Any; the user's table, by set id). Support sets still keep one C.DMG amulet.
  - `scaling.py`: faction types from the 6★ roster: each champion's pull per stat from its
    formulas (damage hits and bombs; for Support-role champions heals, shields, revives:
    `skills.json` `scaling`), each effect counting its shape. Mixed scalers (Rotos, Fellhound)
    and supports healing off ATK (Kurosa) get a type for their faction only. Each mythical
    form counts as a champion of its own (`Tables.hero_forms`). Exceptions go in
    `scaling.OVERRIDES` (`Skip` / `Weigh`, by champion name and form); the
    `champion-exceptions` skill finds candidates with `just exceptions`
    (`optimiser/accessories/scaling_report.py`).
  - `potential.py`: every way a piece can turn out (upgrades at +4/8/12/16 add a substat until
    four, then roll one; a rework keeps each line's roll count, set and faction and re-picks
    main stat and substats; once only: `RerollsCount`), scored in average 6★ rolls, quantile 75.
  - `assess.py`: each piece's value: max(+16, rework) potential × shortage factor (good
    pieces on its set/faction/slot: ×1.15 none … ×0.9 three+) × the set's meta tier
    (`roles.SET_TIERS`: Mercurial, Merciless, Swift Parry 1.3; Feral, Slayer, Pinpoint 1.15; set-less 0.6).
  - `cleanup.py`: inventory + mailbox planned together; the lowest values go until
    `target_free` spaces are left (sold, or left unclaimed). Special variants
    (`VariantId` "Corrupted": unusual stats, a border) are left alone everywhere. Never dropped: protected pieces,
    banners with SPD rolled 3+, good potential (slot's top quarter), each faction's Faction
    Wars reserve, 6★ damage-set amulets not yet reworked (may rework to C.DMG). Group quotas
    (2, 1 for low-value sets) make the surplus go first. Swaps (own tab, by champion): a loose
    piece clearly better than one an unlocked champion wears in the same group is planned as
    equipped (Equip button; the piece coming off may then be sold). Lock champions whose gear must stay.
  - `enhance.py`: roll to +12 (cheap, informative), to +16 (only good pieces), rework lists.
- `webui/`: FastAPI + Jinja + htmx + Pico CSS. `service/` is framework-free (frozen
  dataclass view models, ready to serve as JSON if the UI moves to Vue), a module per page
  (`champions`, `results`, `runs`, `accessories`, `assumptions`) over `current` (paths, the
  cached capture, locks), `views` (champion rows, piece names and art) and `scores` (accessory
  potentials kept in `data/cache/potentials.pickle` by piece state, per scorer and scoring
  code, so only changed pieces are rescored); `forms.py` is the
  form boundary; only `app.py` and `templates/` know about HTTP/HTML.
  Colour palettes (Pico's default and Hana, from `~/repo/demeter`'s `palettes.css`) live in
  `static/palettes.css`: the nav's switcher (`palette.js`) sets `<html data-palette>` and a
  `raid_palette` cookie, which `base.html` reads so pages render in it from the start.

## Commands

The `justfile` wraps these (`just` lists recipes: `proxy`, `static`, `web`,
`web-restart`, `assets`, `check`, `dump`, `schema`, `check-levels`, …; `configure` and
`install` set a machine up, paths in `.env`).

```
./run-proxy.sh                                   # capture (extractor + game running)
./update-static.sh                               # after a game update
uv run python -m webui                           # http://127.0.0.1:8000
uv run --group assets python -I tools/extract_assets.py
uv run --group dev black optimiser webui && uv run --group dev ruff check optimiser webui
uv run --project ~/repo/python-style python-style optimiser webui   # house style checker
```

The web server reloads itself when Python under `optimiser/` or `webui/` changes
(watchfiles; `--no-reload` turns it off); templates and static files are read fresh anyway. Stop it by port (`ss -ltnp 'sport = :8000'`), not `pkill -f` with a pattern
that also matches your own shell command.

## Conventions

Follow `~/repo/python-style` (rules, examples, checker): module docstring maps that name what
the module defines, workflow functions, frozen dataclasses, narrowable unions + `match`
over flags, `Result`-style returns for reportable failures, blank lines around blocks. ruff
and black at line length 100. `tools/*.py` are scripts, outside the style check.
Shell: `grep` is aliased to ugrep, so use `/usr/bin/grep`.

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
- **Great Hall:** per affinity and stat level from the capture's `GreatHall` (values per level,
  not cumulative). **Arena:** the capture's `ArenaLeague` (Gold V +22% HP/ATK/DEF).
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
- HH names sets differently from the game (HH `AttackPowerAndIgnoreDefence` = Cruel); join by
  number via `set_ids.json`. Two placeholder sets (55, 56) are unreleased prototypes, hidden.

## Damage (read from `SharedModel.Battle.Core.DamageCalculator` disassembly)

- `damage = formula × (1 + books) × (1 + hit bonus) × other (1 + x) factors × DEF mult ×
  status-effect reductions × random roll`.
- DEF multiplier = `1 − 0.85 × (1 − e^(−effDEF/1500))`; effDEF = DEF × (1 + defenceModifier);
  defenceModifier = skill's `DefenceModifier` − sets' ignore DEF (they **add**).
- Crit hit bonus = C.DMG + skill crit extra, **no cap** anywhere. C.RATE is a probability.
- Set ignore DEF comes from `ChangeDefenceModifier` passives on set skills: Lethal/Savage share
  skill 100010 (25 %, once); Cruel 5 % × sets; Slayer AoE only; values are multiples of 5 %.
- Skill formulas (`MultiplierFormula`) are mostly `k*STAT`; anything using target/battle
  state (`TRG_HP`, counts) isn't supported.
- `DamageModifierFromStats` applies dealt-damage substats (PvP/boss/dungeon), not modelled yet.

## Solver

MILP in HiGHS (`highspy`). A binary per wearable piece (faction, pool, `above_level` filter),
one per armour slot, ≤ 1 per accessory slot; set bonuses exact via piece-count variables
tied with equalities. Ranking is lexicographic: maximise each goal, then hold it within
`slack` (relative; for damage, applied to damage not its log). Builds after the first exclude
earlier ones with no-good cuts. Dominance pruning drops pieces that ≥ `builds` others in the
same slot/set/faction match or beat on every stat the request uses.

Damage is ranked by its log: tangent lines under log(formula) and log(1 + C.DMG) (20 each,
over the reachable range: fewer, tighter tangents were several times faster); the DEF term
(convex in ignore DEF) is exact with a binary per 5 % step. HiGHS has no MIQP and damage is a
non-convex product anyway, hence the log form. Damage-then-stat solves take ~25 s per build;
the user is fine with that.

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

IL2CPP dump for the current game (11.85.5, metadata v39): `just dump` into `data/dump/11.85.5`,
with the roytu fork of Il2CppDumper (`~/repo/Il2CppDumper` from github.com/roytu/Il2CppDumper,
built with `dotnet build Il2CppDumper/Il2CppDumper.csproj -c Release -f net8.0
-p:RollForward=Major`; set `RequireAnyKey: false` in the output's `config.json`). Method bodies:
disassemble `GameAssembly.dll` at the dump's RVAs (capstone), labelling calls from
`script.json`. Static array initialisers (`<PrivateImplementationDetails>` fields) show their
data's offset in `global-metadata.dat` as `/*Metadata offset 0x…*/` in `dump.cs`.

## Assets

Portraits are named by type id with ascension 0 (`9990`), piece art `<set id>_<slot>`, set
icons by set id. Affinity icons by lower-case affinity, faction banners by the capture's
(HH's) faction name (HH renames Samurai → Shadowkin, Olympians → Argonites; the extractor
pairs them by type), stars `yellow`/`purple`/`red` (plain/ascended/awakened). Fusion
portraits are in `FuseAvatarsLocal`. Set accessories use the set's generic art even when faction-locked; only
set-less accessories use `<faction>_<slot>`. Old sprite names mapped by the user: Berserker = Crit
Damage, Healing = Regeneration, Rage = Killstroke, Stalwart2 = Defiant, Taunting = Provoke,
Warrior = Cruel. Accessory-only sets have no icon. The images are Plarium's art: keep local.
