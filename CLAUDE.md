# raid-optimiser

An experimental, personal gear optimiser for Raid: Shadow Legends: cruder and faster than
HellHades' (HH) optimiser rather than a copy of it. The user pays for HH and keeps using it;
**don't use or port HH's source or algorithms**. Nothing of HH's is used any more but its
extractor, driven for in-game commands (below). The account and the game's tables come from
the game itself.

## Layout

- `data/` (gitignored): everything that isn't code. `captures/` (the snapshot), `game/` (the
  game's tables), `state/` (the store), `cache/` (the reader's layout, accessory scores);
  `optimiser/paths.py` names them. `schema/` (tracked) stays at the top.
- `capture/hh_capture.py` (`just proxy`; `~/scripts/hh.sh` finds the proxy by its command
  line, so keep the file name and argument order): mitmproxy, only for the game commands
  below. The extractor's account uploads pass through untouched; the account comes from the
  reader.
- In game: the addon serves `POST 127.0.0.1:8081/equip` (`{"hero_id", "artifact_ids"}`,
  `EquipArtifacts`) and `/preview` (`{"account_id", "hero_id", "artifact_ids"}`, `PreviewBuild`,
  the game's build preview: nothing changes, no sync follows). It injects the SignalR
  invocation into the extractor's `/reader` hub WebSocket, as if HH's server sent it, then
  waits for (and swallows) the extractor's `HelperRequestResult`. `account_id` is the
  account's user id. `webui/extractor.py` is the client; each build has both buttons.
  `/sell` (`{"artifact_ids"}`, `SellArtifacts(int[])`) only selects the pieces in the game's
  sell screen; the user confirms the sale in game. Only the accessories page sends it, and
  only pieces its current plan sells (`forms.settings.parse_sell`).
- `reader/` (Rust, `x86_64-pc-windows-gnu`; `just read`, ~2.5 s): **the account's source**.
  Reads it out of the running game's memory from outside the process (`OpenProcess` VM_READ +
  `ReadProcessMemory`; nothing injected or written), run in the game's prefix via
  `plarium-umu`, into `data/captures/snapshot.json` (`paths.SNAPSHOT`, `account.load_account`
  parses it; the web UI reloads when it changes; the nav's Sync button runs `just read` through
  `webui/reader.py`, and a successful Equip syncs after). Only what the optimiser uses:
  champions (static facts come from `hero_types.json`), pieces, who wears what, relics, Great
  Hall, arena league, inbox pieces, champion tags (`marker`: `HeroMarker`, one per champion;
  ArenaFirst is "Arena Build I"), gear presets (`gear_presets`: `ExternalArtifactsStorage._presets`,
  per champion or global (`hero_id` null, the game's key -1), artifact or accessory), saved teams (`teams`: presets with their area, from
  `HeroesAiPreset.TypeRanges` as `get_Type` reads it, ids 0/301/601–603 Pvp; classic and 3v3
  arena defenses; empty slots are 0 or -1) and the Chimera's raid (`chimera`:
  `SharedModelManager.DynamicData.StageData.AllianceChimeraData`) and stage progress (`stages`:
  `UserWrapper.Stages` → `UserStageData.BattleResultsByStageId`, stage id → passed and star
  count; the game keeps the count only, not which battle quests earned it). Values are the game's: ids, enums by name (the faction's game
  name: `account.faction_name` gives the display name), Fixed rounded to 6 decimals. A
  module per area (`heroes`, `artifacts`, `relics`, `account`) over `process` (`Block`: an
  object in one read), `il2cpp` (class layout), `collections` (List/Dictionary) and `roots`
  (`AppModel` via its type info → parent `SingleInstance<AppModel>`'s statics; pieces live in
  `ArtifactStorageResolver._implementation`'s `ExternalArtifactsStorage` cache, not
  `UserArtifactData.Artifacts`, which is empty). Offsets and enum names come by name from the
  dump: `tools/reader_layout.py` (`just reader-layout`, rerun after `just dump`) writes
  `data/cache/reader-layout.json`; modules resolve theirs once with `offsets!`. Checked
  against HH's capture: the same account, but HH rounds Corrupted pieces' damage-modifier
  lines to two decimals.
- `just static`: decodes the game's cached static data
  (`LocalLow/Plarium/Raid_ Shadow Legends/static-data/<ver>/<hash>`, the newest file;
  MessagePack-CSharp Lz4BlockArray, string keys: `tools/static_decode.py`, `msgpack` + `lz4`,
  whole-number floats as ints and keys as text, as the old C# decoder's JSON had them) via
  `tools/static_export.py` and `schema/schema.json` (from an IL2CPP dump,
  `tools/gen_schema.py`) into `data/game/{sets,hero_types,bonuses,skills,glyphs,gear,enemies,effect_sources}.json`.
  Enemy skills' block effects (`PassiveBlockEffect`) carry `blocks`: the effect kinds they stop,
  their groups resolved through `static_export.EFFECT_KIND_GROUPS` (12, BossImmunitiesEffects,
  read from the game's code: `EffectKindGroupExtensions..cctor`'s arrays in global-metadata.dat;
  recheck after a game update). Not read yet: it's every boss's immunities (the Chimera's agree
  with `chimera.tags` but for Rage, which that list lacks). Skill placements also carry
  `repeats` (the effect's Count × StackCount), a relic's `relic_level` (its tier: the relic
  skill level it's for, from `relicSkillLevel==N`) and `echo` (a status it places again when
  one is placed, from `StatusEffectWithTypeIdIsApplied`); `effect_sources.json` has
  `relic_skill_levels` (`SkillLevelByRelicLevel`: relic level 0/6/9/12/15/18 → skill level 1–6).
- `optimiser/levels.py`: base stats at any rank/level, computed as the game does (below);
  `tools/check_levels.py` checks its table is still in the game's metadata (`just static`)
  and, given a raider oracle table, compares results. `tools/oracle_request.py` /
  `tools/oracle_import.py` drive the oracle (below), now for checking only.
- `optimiser/enemies.py`: the enemy store (`data/game/enemies.json`, types' base stats from
  `hero_types.json`): every stage's formations, team restrictions (every champion must match;
  `MinCount`/`MaxCount` are the team size), stat modifiers (stage-wide and per slot: a relative
  `value` multiplies base by 1 + value, checked against the Chimera's listed HP; slot modifiers
  give UNM clan boss its 190 SPD / 225 RES / 225 ACC; a stage modifier reaches a wave's bosses
  if `boss_only`, else its other enemies, never both: `BossOnly == heroType.IsBoss`, the type
  having `BossData`, in `BattleBonuses.InitModifiers`; slot modifiers always apply), the areas
  (`Area`/`Region`: display names, stages in order per difficulty), boss kinds, enemy skills, clan boss tiers,
  the Chimera (forms in type order Ultimate/Ram/Lion/Snake, form sequence, trials with targets
  from their hidden `StartChallenge` skills) and per-area shield caps. `enemy_stats` is stats as
  a battle starts (no in-battle passives). `just enemies` (`optimiser/enemy_report.py`) prints it.
  The co-op event world boss (Tainted Demon Lord) is area `CooperationEventWorldBoss`.
- Teams (`optimiser/teams/`): finding a team by what its champions bring, against `Goals`:
  objectives (each its needs, a `Target` they're met against: a name for labels and the
  debuffs it's immune to, and `requires`: an objective met first), extras every team brings
  (one of some tags, or so many different debuffs or buffs; against `extras_target`) and a
  team `size`. Judged on what champions can place and do, not damage, nor turn order, nor ACC
  against RES. `find` is the entry point: `check_slots`, `find_teams` (from a pool of
  champions: `kits.candidates`, filtered by the page) → `Found`.
  - `tags`: `Tag` (debuff/buff status kind with strengths merged by `status_kind`, a skill
    effect from the curated `EFFECT_LABELS`, or a `Mechanic`), `Target`; `tag_label(tag,
    enemy)` ("Decrease DEF on the Chimera").
  - `needs`: `AnyOf`, `Distinct` (debuffs the target isn't immune to, `counts_toward`;
    `instances`: each different debuff counts one, each champion's Poisons as many as one of its
    skills places, `Kit.counts` from placements' `repeats` (Count × StackCount), and a Toxic set
    allowed for any champion one more, `Distinct.gear`; unless they `accumulate` over the fight:
    the Chimera's, where the team gets several turns to each of its own and any Poison source
    meets it, given speed), `Given`; `Requirement` (a need and its target), `Objective`,
    `Goals`.
  - `kits`: a champion's `Kit` from `skills.json` (`placements`, `books`, `effect_kinds`,
    `target_hp_damage`), all forms of a mythical, each tag's best `Rating` = uptime (turns ÷
    cooldown less cooldown books; passives and A1s every turn; instant: 1 ÷ cooldown) ×
    reliability (chance + chance books, × `CONDITIONAL` if gated) × reach (`REACH_TEAM`/`ALLY`/
    `SELF`; debuffs, mechanics and enemy-side effects in full), × `OTHER_FORM` for a
    mythical's other form. Own skill levels count (`Cast`). Each placement's `on_boss`
    (`static_export.on_boss`: its effect and target conditions read three-valued with the
    boss atoms, `BOSS_FACTS`, true) drops what never lands on a boss (Lamasu's True Fear goes
    to non-bosses; bosses get Decrease SPD), and only what depends on more is `CONDITIONAL`:
    ratings are against a boss. Secret skills (`ShowSecretSkill`, Mortu-Macaab's Peril) are
    rated as if cast every turn, not at the passive's chance. `wantable(account, never)`.
  - `gear`: `effect_sources.json` (each set's set skills, each relic type's skills and faction
    skills, factions by display name) → `Gear` options (every set, relics the account owns,
    `Account.relic_types`; `gear_options(…, never)`), rated like skills. Allowed ones
    (`gear=<Gear.key>`, `gear_set` marks the list as sent; default `DEFAULT_GEAR`, Toxic) and
    team-wide assumptions make needs `Given` (`with_gear`); faction relic skills (Bloatshield
    Totem's Demonspawn reflect) and per-champion assumptions (`assume=<champion id>@<tag key>`)
    join those kits (`equip`). Gear doesn't count toward "N different" needs. Relics count only
    their tier (team gear: the best copy owned, `best_level`). A team slot's champion wears
    relics (`worn_relic` → `wear`; `find.Worn`, a tuple per slot): their skills at the copy's
    level, and an echo (Sporeburst Rod: a placed Poison may place another) multiplies the
    champion's own count by 1 + its chance (`Kit.counts` are floats: 2 Poisons → 2.5); echoes
    alone bring nothing, so the rod isn't team gear.
  - `cover`: who covers what (`Lineup`, `ObjectiveCover`), the members a team needs
    (`core_of`), the score: a team's sources of a tag combine as 1 − Π(1 − s); a need scores
    its best tag (a count: its best N's mean; `Given`: the gear's rating); `team_score` is the
    mean over `Goals`' requirements and ranks the options (`ranking`: then fewest champions,
    then strength).
  - `search`: `every_team` lists every minimal team meeting every objective and bringing the
    extras (branch on the unmet need fewest champions bring; "any champion" fills the rest),
    within `SEARCH_BUDGET` (20,000 teams or 1 s: for the Chimera with nothing pinned there are
    hundreds of thousands, mostly from the "N different" trials); if none meets them all,
    `partial_teams` (HiGHS) gives the best partial ones.
- Team finder (`/teams`, `webui/service/teams.py`, `forms/teams.py`, `teams.html`): base needs
  (none, or a Faction Wars stage's challenge: `base=fw&crypt=<region>&stage=<n>`, linked from
  the Info page's stages; the Chimera's trials are the Chimera page) plus what's asked besides
  (tags, counts), every team of five meeting them all. `optimiser/factionwars.py`: crypts
  (`crypts`, the faction each admits: only its champions are searched) and a stage's challenge
  (its last quest) as needs, from its text (`QUEST_NEEDS`: "Place 10+ Stun" asks for a Stun;
  counts aren't modelled, reliability is), against `ENEMIES` (no immunities). Fight quests
  (turns, losses, weak hits, damage) and make-up ones (3 Epic champions) aren't checked: the
  page says so. Hex is the `Mark` status, Perfect Veil `Invisible2`, Bomb `TimeBomb`.
- Chimera trials (`/chimera`, `optimiser/chimera/`): one team of five that clears a whole
  column (Wing/Tail/Paw: where this raid's mythical materials are; the game doesn't name its
  columns, so the page names each by its Easy Ram trial's statuses) in all three animal forms, Easy→Normal→Hard, in one UNM fight (rewards
  only count for trials cleared in the same fight), found by `optimiser.teams`. Targets are
  shown, not checked.
  - `tags`: the Chimera's immunities, `BOSS_IMMUNE` minus `FORM_ALLOWS` (Ram takes Fear, Snake
    Block Active Skills; `NEVER_LANDS`, `only_in`), and its targets: `form_target(form)` for a
    trial, `ANY_FORM` for the extras.
  - `trials`: `trial_needs` (a `match` per trial; counts from the trial's target or `rules`),
    checked against the trial's own status list (`check_needs`; the page warns on a
    mismatch). The `DEBUFF_COUNT>=` trials (Lion Wing Easy, Lion Paw Normal, Snake Wing Hard)
    count instances (`Distinct.instances`, `accumulates`).
  - `plan`: `check_lineup` (the slots alone) and `fill_lineup` (`teams.find`), from a `Brief`
    (column, wanted, loadout, counts); `column_goals` makes the column's trials objectives (keyed by the
    trial's skill, waiting on the one above), and `Plan.trials` maps them back for the board.
  - `rotation`: which trial gives what this raid, read from the game's code
    (`ChimeraExtensions.GetChimeraChallengeRewardWithOffset`, `GetPrizeOffset`): a tier's 9
    reward lists (`enemies.json`, game order Ram/Lion/Snake × Wing/Tail/Paw) shift over the
    trials, trial i getting list `(i + offset) % 9` at its level. The offset is the raid's
    `PrizeOffset` from 24 h after its start (`hours_between_raids - activity_hours`), the
    previous one's before. Offset 0 puts the Mythical materials on Tail, so the column is
    Tail/Wing/Paw for offset % 3 = 0/1/2 (`mythical_column`; checked against the game: offset
    2, Paw). The page's default column.
  - Page (`webui/service/chimera.py`; `forms.chimera.parse_chimera` is its boundary, `ChimeraRequest`
    with `team: TeamAsk` and `fill: Fill | None`): rotation, slots (`slot` ×5, "Name, 6★ L60 #id" from the champion
    finder, or part of a name in the URL), "Also bring" (`want=<Tag.key>`, from `wantable`), gear, relics &
    assumptions, Run (3 options, 9 more per "show more", at most 300; `option` picks the one
    the grid shows; "Use this team" puts it in the slots), then the board (a row per form, its three trials across).
    State is all in the URL. Icons: `chimera/<Form>_<Level>` (ChimeraChallengeIcons), from
    `tools/extract_assets.py`.
- Team finder parts, shared by pages that find teams (the team finder and the Chimera page):
  the slots (each a `relic` field: empty for what the champion wears now, "none", or a relic
  id; the dropdown lists each owned relic type's best copy; a new champion starts from what's
  worn: the finder's `data-finder-reset`), "Also bring" (with counts: `count=debuff:3`, so
  many different) and gear, relics & assumptions panels and each need's row. `forms/team.py`
  (`parse_team` → `TeamAsk`: picks, wanted, loadout, counts, relics; `Offers`, with the relic
  types; a search's shape: `Fill`, `parse_fill`, `GRADES`), `service/team.py` (`slot_worn`:
  each slot's relics as gear),
  `service/team.py` (`TeamView`,
  `team_view(…, enemy, note)`: the want groups name the enemy, `note` says where a tag only
  lands; `need_view`, `slot_view`), `templates/_team.html` (`team_slots`, `wants_panel`,
  `gear_panel`, `need_item`, `status_icon`, `score_pill`; a chip's × links to the page's
  `without(key)` macro, passed in) and `static/picker.js` (a search over what isn't chosen,
  grouped by kind; a pick adds a field and reloads, showing it as a removable chip). Icons:
  `statuses/` (StatusEffectIcons, by status kind; `service.team.icon_name` maps ours, e.g.
  DecreaseDefence → StatusReduceDefence). Class names and the champion datalist's id still
  say chimera.
- `just dump`: Il2CppDumper over the installed game into `data/dump/<game version>`
  (`dump.cs`, `script.json`): `just schema`'s input and the source of RVAs to disassemble.
- `tools/extract_assets.py`: portraits, set icons and piece art from the game's Unity bundles
  (UnityPy) into `webui/static/assets/`.
- `optimiser/`: the model and solver (`account`, `stats`, `damage`, `solve`, `assume`, `glyphs`,
  `labels`), `paths` (where the data lives) and `settings` (the store's rows as the model's
  types: the only model module besides `store` that touches the file).
- `optimiser/store.py`: user state the snapshot doesn't hold, in SQLite at `data/state/optimiser.sqlite`
  (stdlib `sqlite3`): champion locks 1–5, set on the champion list, and reserve rules
  (`optimiser/reserve.py`, by `rule_key`: `Tagged(marker)` what champions with a tag wear,
  `GlobalPresets` every global gear preset's pieces even unworn, `Team(preset id)` what a saved
  team wears; what they reserve comes from each snapshot; edited on the Config page, `/config`). A solve's `GearFilter`
  says what gear it may not take, each part toggled on its own on the champion page: each reserve
  rule (`exclude_<rule key>`, on by default), champions locked above a level, anything other
  champions wear. Taken pieces note what reserves them. The champion's own gear is always
  allowed. Locks are kept for now, to compare.
  Also what solves assume (account-wide, the Config page `/config`, once `/assumptions`; `optimiser/assume.py`): flags for
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
  inventory space (2200 for accessories); overflow waits in the mailbox (the inbox's
  pieces, `Account.mailbox`).
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
    (`VariantId` "Corrupted": unusual stats, a border) are left alone everywhere. Never dropped: protected pieces, reserved pieces (swaps may still move them),
    banners with SPD rolled 3+, good potential (slot's top quarter), each faction's Faction
    Wars reserve, 6★ damage-set amulets not yet reworked (may rework to C.DMG). Group quotas
    (2, 1 for low-value sets) make the surplus go first. Swaps (own tab, by champion): a loose
    piece clearly better than one an unlocked champion wears in the same group is planned as
    equipped (Equip button; the piece coming off may then be sold). Lock champions whose gear must stay.
  - `enhance.py`: roll to +12 (cheap, informative), to +16 (only good pieces), rework lists.
- Nav (`base.html` `sections`): Optimiser, Accessories, Teams, Info; a section with several pages
  shows them as tabs under the bar. Optimiser: the champion list, the champion last solved for
  (`store.latest_champion`), Config. Teams: Finder (`/teams`), Chimera. Info: Faction Wars
  (`/info`), Empower (`/empower`).
- Info page (`/info`, `webui/service/info.py`): the account's progress from the snapshot.
  Faction Wars Hard: per crypt, stages short of their stars and the battle quests they may still
  need (`enemies.json` stages' `quests`, texts from `BattleQuestData`; a stage one star short is
  missing one of the two after "Beat Stage", shown as its challenge "or 5 Champions, no losses").
- Champion finder (`webui/service/finder.py`, `forms/finder.py`, `_finder.html`,
  `_finder_results.html`, `static/finder.js`, route `/finder`): a dialog a page includes, opened
  by any button marked `data-finder`; name, rarity and fewest stars filter the account's
  champions (htmx). A pick goes to the champion's optimiser, or with `data-finder="slot"` fills
  the field `data-finder-target` names with the pickers' "Name, 6★ L60 #id" (`views.
  choice_label`) and submits its form. Used by the champion page's Switch champion and the
  Chimera slots (+ when open, Change when filled; their `slot` fields are hidden).
- Target picker (`webui/service/targets.py`, `forms/targets.py`, `_target_picker.html`,
  `static/target.js`, route `/targets`): a reusable component, top of the champion page. Zone
  (`ZONES`: Dungeons, Clan Boss from its tiers × affinities, Faction Wars, Hydra, Doom Tower,
  Grim Forest, Cursed City, co-op Demon Lord, Campaign) → group (region; shared names get what
  tells their ids apart) → difficulty → stage, then one enemy of the last wave (boss, else most
  HP). htmx re-renders it on change (`HX-Trigger-Name`: lower levels reset); a user's pick fires
  `target:picked` (the champion page sets `enemy_def`); its hidden `target`
  ("stage:wave:slot", `form="request"`) is saved with runs and restored quietly. The panel dims
  when `enemy_def` no longer matches it.
- `webui/`: FastAPI + Jinja + htmx + Pico CSS. `service/` is framework-free (frozen
  dataclass view models, ready to serve as JSON if the UI moves to Vue), a module per page
  (`champions`, `results`, `runs`, `accessories`, `assumptions`) over `current` (paths, the
  cached account, locks), `views` (champion rows, piece names and art) and `scores` (accessory
  potentials kept in `data/cache/potentials.pickle` by piece state, per scorer and scoring
  code, so only changed pieces are rescored); `forms/` is the form boundary (`request`: the
  solve form and build buttons, `settings`: the forms that change the store, `chimera`, and
  `common`: `FormErrors`); `result.py` is the `Err`/`Result` that `extractor.py` and
  `reader.py` return; only `app.py` and `templates/` know about HTTP/HTML.
  One theme, Vault, in `static/theme.css` (dark only: `base.html` sets Pico's `data-theme="dark"`).
  The look (◆ section titles) follows the Stitch design system the
  user supplied, but keeps Alegreya (headings) and Alegreya Sans (text), the user's choice over
  the spec's fonts. `static/app.css` opens with a base layer
  over Pico (short controls, no margins on controls or sections: layouts space with `gap`;
  tables headed in caps on whatever holds them; cards with a rim, no shadow) and the shared
  components: `panel`/`panel-head`, `well`, `table-well`, `caps`, `badge` (`good`/`bad`/
  `info`), `chip` (`on`), `status` (`met`/`missing`), `segmented`, `slot` (`empty`),
  `stat-tiles`, `switch-rows`, `page-head`, `page-tabs` (a badge for a count), `tally`, `cta`,
  `danger` (selling), `champion-strip`, `gear-pair` (`gear-card` `candidate`/`worn` over the optimiser's `piece` card), `meter`,
  `weight-chip`. Build pages from those rather than overriding Pico per element.

## Commands

Use the `justfile` (`just` lists every recipe). It is the only place that knows machine paths
(`.env` overrides its defaults) and passes them to the tools as arguments.

```
just install          # set a machine up (paths, mitmproxy's CA, then update)
just update           # after a pull, game update or HH update: deps, HH patch, static, assets
just read             # the account, from the running game's memory (read-only)
just proxy            # the HH extractor's game commands: equip, preview, sell (extractor + game running)
just static           # re-export the game's tables (part of update)
just schema-refresh   # when the export says the dump predates the game: dump, schema, static
just web              # http://127.0.0.1:8000 (web-restart, web-stop)
just assets           # portraits and icons from the game's bundles (part of update)
just check            # black + ruff over all Python, then the house style checker
uv run --group dev pytest   # tests/ (not part of just check)
```

The web server reloads itself when Python under `optimiser/` or `webui/` changes
(watchfiles; `--no-reload` turns it off); templates are compiled afresh per render (no Jinja cache: it missed changes to imported templates) and static files are read fresh anyway. Stop it by port (`ss -ltnp 'sport = :8000'`), not `pkill -f` with a pattern
that also matches your own shell command.

## Conventions

Follow `~/repo/python-style` (rules, examples, checker): module docstring maps that name what
the module defines, workflow functions, frozen dataclasses, narrowable unions + `match`
over flags, `Result`-style returns for reportable failures, blank lines around blocks. ruff
and black at line length 100, over `optimiser webui capture tools` (`just check`). `tools/` is a
package of click commands run as `uv run python -m tools.<name>`: paths come in as arguments,
never hard-coded, and the project's own paths from `optimiser.paths`. `capture/hh_capture.py`
runs inside mitmproxy (`uv run --group capture`), so it stays standalone.
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

IL2CPP dump for the current game (11.85.5, metadata v39): `just dump` into `data/dump/11.85.5`,
with the roytu fork of Il2CppDumper (`~/repo/Il2CppDumper` from github.com/roytu/Il2CppDumper,
built with `dotnet build Il2CppDumper/Il2CppDumper.csproj -c Release -f net8.0
-p:RollForward=Major`; set `RequireAnyKey: false` in the output's `config.json`). Method bodies:
disassemble `GameAssembly.dll` at the dump's RVAs (capstone), labelling calls from
`script.json`. Static array initialisers (`<PrivateImplementationDetails>` fields) show their
data's offset in `global-metadata.dat` as `/*Metadata offset 0x…*/` in `dump.cs`.

## Assets

Portraits are named by type id with ascension 0 (`9990`); enemies' (bosses, Hydra heads, from
`HeroAvatars_Bosses`/`HeroAvatarsHydra`) by full type id, via their type's `avatar`. Piece art `<set id>_<slot>`, set
icons by set id. Affinity icons by lower-case affinity, faction banners by display name
(`account.FACTION_NAMES`: Samurai → Shadowkin, Olympians → Argonites), stars `yellow`/`purple`/`red` (plain/ascended/awakened). Fusion
portraits are in `FuseAvatarsLocal`. Set accessories use the set's generic art even when faction-locked; only
set-less accessories use `<faction>_<slot>`. Old sprite names mapped by the user: Berserker = Crit
Damage, Healing = Regeneration, Rage = Killstroke, Stalwart2 = Defiant, Taunting = Provoke,
Warrior = Cruel. Accessory-only sets have no icon. The images are Plarium's art: keep local.
