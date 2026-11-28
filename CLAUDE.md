# raid-optimiser

An experimental, personal gear optimiser for Raid: Shadow Legends: cruder and faster than
HellHades' (HH) optimiser, not a copy of it. The user pays for HH and keeps using it;
**don't use or port HH's source or algorithms**. Only HH's extractor is still used, driven for the
in-game commands below; the account and the game's tables come from the game itself.

## Layout

- `data/` (gitignored): everything that isn't code. `captures/` (the snapshot), `game/` (the
  game's tables), `state/` (the store), `cache/` (the reader's layout, accessory scores);
  `optimiser/paths.py` names them. `schema/` (tracked) stays at the top.
- `capture/hh_capture.py` (`just proxy`; `~/scripts/hh.sh` finds the proxy by its command
  line, so keep the file name and argument order): mitmproxy, only for the game commands
  below. The extractor's account uploads pass through untouched; the account comes from the
  reader.
- In game: the addon serves `POST 127.0.0.1:8081/equip` (`{"hero_id", "artifact_ids"}`,
  `EquipArtifacts`; a successful Equip syncs the account after) and `/preview`
  (`{"account_id", "hero_id", "artifact_ids"}`, `PreviewBuild`: the game's build preview, so
  nothing changes and no sync follows). It injects the SignalR
  invocation into the extractor's `/reader` hub WebSocket, as if HH's server sent it, then
  waits for (and swallows) the extractor's `HelperRequestResult`. `account_id` is the
  account's user id. `webui/extractor.py` is the client; each build has both buttons. Equip sends the gear rules
  the build was found under (a run's `gear_fields`, Team gear's `filter_form` and its team) and
  is refused if the account has moved on since: a piece now on a champion those rules keep it
  from, at today's locks, or newly reserved (`results.check_equip`; a solve can't see pieces
  another build is about to take, so two builds solved before either is equipped can clash).
  `/sell` (`{"artifact_ids"}`, `SellArtifacts(int[])`) only selects the pieces in the game's
  sell screen; the user confirms the sale in game. Only the accessories page sends it, and
  only pieces its current plan sells (`forms.settings.parse_sell`).
- `reader/` (Rust, `x86_64-pc-windows-gnu`; `just read`, ~2.5 s): **the account's source**.
  Reads it out of the running game's memory from outside the process (`OpenProcess` VM_READ +
  `ReadProcessMemory`; nothing injected or written), run in the game's prefix via
  `plarium-umu`, into `data/captures/snapshot.json` (`paths.SNAPSHOT`, `account.load_account`
  parses it; the web UI reloads when it changes; the nav's Sync button runs `just read` through
  `webui/reader.py`, its Watch button `just watch`, detached, found by its processes). Only what the optimiser uses: champions (static facts from `hero_types.json`;
  unspent mastery scrolls, `scrolls`: `HeroMasteryData.CurrentAmount`), pieces, who wears what,
  relics, Great Hall, arena league, inbox pieces, champion tags (`marker`: `HeroMarker`, one per
  champion; ArenaFirst is "Arena Build I"), gear presets (`gear_presets`:
  `ExternalArtifactsStorage._presets`, per champion or global (`hero_id` null, the game's key -1),
  artifact or accessory), saved teams (`teams`: presets with their area, from
  `HeroesAiPreset.TypeRanges` as `get_Type` reads it, ids 0/301/601–603 Pvp, and each slot's
  skill settings, `priorities`: as the 3v3 defenders', `account.SkillSettings`; classic and 3v3 arena
  defenses, each 3v3 defender's skill settings (`arena3x3_priorities`: its slot's
  `PrioritiesSetup`, the game's settings in its `sequences`: openers and `SkillPriorityType` by
  skill id); empty slots are 0 or -1), the Chimera's raid (`chimera`:
  `SharedModelManager.DynamicData.StageData.AllianceChimeraData`) and stage progress (`stages`:
  `UserWrapper.Stages` → `UserStageData.BattleResultsByStageId`, stage id → passed and star count;
  the game keeps the count only, not which battle quests earned it), and the server's battle
  settings (`battle_settings`: `SharedModelManager.GameParameters.BattleSettings`, what changes how
  a fight plays out, under the game's field names, for the battle host); for the host too, each
  champion's Blessing (`blessing`: `HeroDoubleAscendData.BlessingId`), each relic's `sockets` and
  the account's `relic_stones`, the Academy's guardians (`academy_guardians`: faction → rarity →
  slots), and each stat line's raw `Fixed` values. Events go to a file of their
  own (`paths.EVENTS`, `data/captures/events.json`: they change far more often): what's
  on as the game's own JSON, `GlobalEventsWrapperReadOnly.DataJson`, kept whole, and the account's
  progress per event's quest, `UserQuestData.OpenedStates`: a solo event's points are its
  `EventsProgress` summed, its `ByPoints` staying 0; a tournament's its `GlobalRatingInfo`'s,
  with its place once the server has sent it; and the texts the server sends for them in the
  player's language, `AppModel.GlobalEventsExternalLocalizationStorage._storage`, a
  `ConcurrentDictionary<int, string>`: `collections::concurrent_dict_refs`); and `summons`
  (`reader/src/summons.rs`): the shards held (`UserShardData.Shards`) and the server events
  boosting a shard type (`ServerEvent.Shards`: drop rules standing in for its own while they
  run). Not the account's mercy counters: the server keeps them (`SummonResults` is the last
  summon's). `just watch`
  (`reader/src/watch.rs`) keeps both current while the game runs: the events every 5 s, the
  account once a fingerprint of it (power, experience, resources spent, silver gained:
  `UserAccount`) has moved and stood still 20 s; each file rewritten only when it changes. Not
  `ServerTimeManager._lastServerTime`: the client's periodic requests move it. It waits for the
  game, and its recipe stops the reader on exit (the reader outlives its launcher otherwise).
  The Events page polls every 15 s. Values are the game's: ids,
  enums by name (the faction's game name, its `tables.faction_name`), Fixed rounded to 6 decimals.
  A module per area (`heroes`, `artifacts`, `relics`, `account`) over `process` (`Block`: an
  object in one read), `il2cpp` (class layout), `collections` (List/Dictionary) and `roots`
  (`AppModel` via its type info → parent `SingleInstance<AppModel>`'s statics; pieces live in
  `ArtifactStorageResolver._implementation`'s `ExternalArtifactsStorage` cache, not
  `UserArtifactData.Artifacts`, which is empty). Offsets and enum names come by name from the
  dump: `tools/reader_layout.py` (`just reader-layout`, part of `just update`) writes
  `data/cache/reader-layout.json`; modules resolve theirs once with `offsets!`. Checked
  against HH's capture: the same account, but HH rounds Corrupted pieces' damage-modifier
  lines to two decimals.
- `just static`: decodes the game's cached static data
  (`LocalLow/Plarium/Raid_ Shadow Legends/static-data/<ver>/<hash>`, the newest file;
  MessagePack-CSharp Lz4BlockArray, string keys: `tools/static_decode.py`, `msgpack` + `lz4`,
  whole-number floats as ints and keys as text, as the old C# decoder's JSON had them) via
  `tools/static_export.py` (its parts `static_convert`, `static_tables`, `static_skills`,
  `static_stages`) and `schema/schema.json` (from an IL2CPP dump,
  `tools/gen_schema.py`) into `data/game/{sets,hero_types,bonuses,skills,glyphs,gear,enemies,effect_sources,items,shards,levelling,loot}.json`
  (`items`: the black market's item names by id, for event prizes; `shards`: each shard type's
  affinities and odds by rarity, with their mercy; `levelling`: the XP each level takes by grade,
  `HeroExperienceByKey`, and a brew's XP, more on its own affinity; `loot`: each stage's gear, by
  region and difficulty, from its `Reward`: pieces a run drops and their odds by rank and rarity). `just schema` also writes
  `schema/events.json` (`--root UpdatableGlobalEventsData --root GlobalEventInterfaceSettingsDto
  --attribute Json`: the `[Json]` keys of the events' JSON and of the interface settings JSON
  within each, which `optimiser.events` decodes the snapshot's by).
  Hero types carry their `auras` (`LeaderSkills`: stat, value, flat or not, and the area,
  affinity, faction and rarity they're held to, null for any; `tables.Aura`, read by the
  optimiser's battle).
  Enemy skills' block effects (`PassiveBlockEffect`) carry `blocks`: the effect kinds they stop,
  their groups resolved through `static_stages.EFFECT_KIND_GROUPS` (12, BossImmunitiesEffects,
  read from the game's code: `EffectKindGroupExtensions..cctor`'s arrays in global-metadata.dat;
  recheck after a game update). Not read yet: it's every boss's immunities (the Chimera's agree
  with `chimera.tags` but for Rage, which that list lacks). Skill placements also carry
  `repeats` (the effect's Count × StackCount), a relic's `relic_level` (its tier: the relic
  skill level it's for, from `relicSkillLevel==N`) and `echo` (a status it places again when
  one is placed, from `StatusEffectWithTypeIdIsApplied`); `effect_sources.json` has
  `relic_skill_levels` (`SkillLevelByRelicLevel`: relic level 0/6/9/12/15/18 → skill level 1–6).
- `optimiser/levels.py`: base stats at any rank/level, computed as the game does (its model, with
  damage, resist, the solver, the oracle and asset naming, in `docs/game-model.md`);
  `tools/check_levels.py` checks its table is still in the game's metadata (`just static`)
  and, given a raider oracle table, compares results; `tools/oracle_request.py` /
  `tools/oracle_import.py` drive the oracle.
- `optimiser/enemies.py`: the enemy store (`data/game/enemies.json`, types' base stats from
  `hero_types.json`): every stage's formations, team restrictions (`team_restriction`: one
  condition holds every champion, as `HeroesSquadContext.ConditionForSlot` reads it; several
  are Cursed City's, one active per stage by the account's `ActiveConditionByStageId`, not
  read: `Rotating`; a condition's `grade` is the fewest stars, its `race` unchecked; Faction
  Wars stages list none, their crypt's faction is the restriction, from the region id), stat modifiers (stage-wide and per slot: a relative
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
    (`static_skills.on_boss`: its effect and target conditions read three-valued with the
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
- Team finder (`/teams`, `webui/service/teams.py`, `forms/teams.py`, `pages/Teams.vue`): what the
  team is against — anything, or a stage from the target picker (`teams.content` resolves its
  `target` first, as the Chimera narrows the offers): a Faction Wars stage's challenge (linked from
  the Info page's stages, `teams.stage_url`), the Chimera's column of trials (`column=`; below), and
  any stage's restriction (only who it admits is searched) — plus what's asked besides (tags,
  counts), every team of five meeting them all. `optimiser/factionwars.py`: crypts
  (`crypts`, the faction each admits: only its champions are searched) and a stage's challenge
  (its last quest) as needs, from its text (`QUEST_NEEDS`: "Place 10+ Stun" asks for a Stun;
  counts aren't modelled, reliability is), against `ENEMIES` (no immunities). Fight quests
  (turns, losses, weak hits, damage) and make-up ones (3 Epic champions) aren't checked: the
  page says so. Hex is the `Mark` status, Perfect Veil `Invisible2`, Bomb `TimeBomb`.
- Chimera trials (a Chimera stage in the team finder; `/chimera` redirects there,
  `optimiser/chimera/`): one team of five that clears a whole
  column (Wing/Tail/Paw: where this raid's mythical materials are; the game doesn't name its
  columns, so the page names each by its Easy Ram trial's statuses) in all three animal forms, Easy→Normal→Hard, in one fight at the stage's tier
  (`trials.stage_tier`; UNM by default) (rewards
  only count for trials cleared in the same fight), found by `optimiser.teams`. Targets are
  shown, not checked.
  - `tags`: the Chimera's immunities, `BOSS_IMMUNE` minus `FORM_ALLOWS` (Ram takes Fear, Snake
    Block Active Skills; `NEVER_LANDS`, `only_in`), and its targets: `form_target(form)` for a
    trial, `ANY_FORM` for the extras.
  - `trials`: `trial_needs` (a `match` per trial; counts from the trial's target or `rules`),
    checked against the trial's own status list (`check_needs`; the page warns on a
    mismatch). The `DEBUFF_COUNT>=` trials (Lion Wing Easy, Lion Paw Normal, Snake Wing Hard)
    count instances (`Distinct.instances`, `accumulates`).
  - `plan`: `column_goals`, from a `Brief` (column, wanted, loadout, counts, tier), makes the
    column's trials objectives (keyed by the trial's skill, waiting on the one above) for the
    finder's search, and its trials by skill map them back for the board.
  - `rotation`: which trial gives what this raid, read from the game's code
    (`ChimeraExtensions.GetChimeraChallengeRewardWithOffset`, `GetPrizeOffset`): a tier's 9
    reward lists (`enemies.json`, game order Ram/Lion/Snake × Wing/Tail/Paw) shift over the
    trials, trial i getting list `(i + offset) % 9` at its level. The offset is the raid's
    `PrizeOffset` from 24 h after its start (`hours_between_raids - activity_hours`), the
    previous one's before. Offset 0 puts the Mythical materials on Tail, so the column is
    Tail/Wing/Paw for offset % 3 = 0/1/2 (`mythical_column`; checked against the game: offset
    2, Paw). The page's default column.
  - In the finder (`webui/service/chimera.py`): the column picker, then the finder's own slots,
    "Also bring", gear and Run, then the board (`TrialBoard`: a row per form, its three trials
    across; `TrialGlance` on each option card). Icons: `chimera/<Form>_<Level>`
    (ChimeraChallengeIcons), from `tools/extract_assets.py`.
- Team gear (`/team-gear`, `webui/service/team_gear.py`, `forms/team_gear.py`,
  `pages/TeamGear.vue`): up to five champions (the team slots) geared at once against the target
  picker's enemy, each a compact row: up to two sets, SPD/ACC/C.RATE minimums and one goal
  (a stat, a skill's damage against the target's DEF, or a rate: debuffs landing against its
  RES, resisting its ACC: `accuracy.Lands`/`Resists`, ranked as the stat capped where the rate
  stops rising). A minimum left out of the URL takes its
  default: ACC `accuracy.accuracy_for_floor` for a champion who places debuffs (`kits`), C.RATE
  100 % for one ranking damage; `res` carries the RES those came from, so ACC still at its default
  follows a new target. RES has no default, just `resistance_for_cap` as the field's placeholder
  (both functions and the points they're at: Resist in `docs/game-model.md`).
  Each ACC/RES field and build shows its resist chances. State rides in the URL, kept in the
  browser as the finder's is (not `run`); the rows are edited in the page and sent with the next
  change (a slot, a rank, a target picked) or Find gear (`run`, the only thing that solves), by
  field names the parser defines and the views carry (`RowFields`, `minimum_field`, `PageFields`,
  `exclude_field`), so the page spells none itself; a build per champion, with the champion page's
  Equip/Preview buttons (`BuildDetail`). `solve.find_team_builds`:
  slot order is priority, each champion's best build alone from what the earlier ones left,
  kept if the rest still meet their limits together (one model, minimums only), else the
  next best, `LEAVING_TRIES` in all, then that step solved with the rest in one model. One
  model ranking every goal in turn gave the same builds within 0.5 % but took minutes (the
  optimality proofs); this takes ~15-20 s for five with damage. A team's own gear counts as
  each member's; pieces teammates wear stay wearable. No team: `Unmet` (who can't alone,
  `Shortfall`s) or `Clash`. The target stage's restriction holds the champion finder to what it
  admits and flags slotted champions it doesn't. Each team the finder finds links here ("Gear this
  team", `teams.gear_url`: its champions in the slots, against the stage's enemy picked).
- Team finder parts (the finder's; Team gear borrows `TeamSlots`, which emits `place` and `wear`
  for it, each page visiting with its own state): `TeamSlots`' slots — each a `relic` field: empty
  for what the champion wears now, "none", or a relic id, the dropdown listing each owned relic
  type's best copy, a new champion starting from what's worn — then "Also bring" (with counts:
  `count=debuff:3`, so many different), the gear, relics & assumptions panels, and each need's row.
  `forms/team.py` (`parse_team` → `TeamAsk`: picks, wanted, loadout, counts, relics; `Offers`, with
  the relic types; a search's shape: `Fill`,
  `parse_fill`, `GRADES`), `service/team.py` (`TeamView`, `team_view(…, enemy, note)`: the want
  groups name the enemy, `note` says where a tag only lands; `need_view`, `slot_view`,
  `slot_worn`: each slot's relics as gear). In Vue: `BringPanels` (chips, `TagPicker`: a search
  over what isn't chosen, grouped by kind;
  the count and assume forms), `RunBar`, `TeamOptions`/`OptionCard` (a slot for the Chimera's
  glance), `NeedsPanel` (a slot for the Chimera's trial rows: `TrialBoard`), `NeedItem`, `StatusIcon`,
  `ScorePill`. Their state rides in the query (the server reads only that): a change starts from
  `TeamLinks.current` (the state as a form would send it; `composables/teamQuery.ts`), edits it
  and visits the page (`preserveState`); a chip's × is `links.without[key]`. The query is kept
  in localStorage per page (`composables/keptQuery.ts`: each visit's saved, a bare visit goes
  to the saved one; "Empty all" forgets it); it stays in the address bar.
  URLs are built in Python: `service.team.PageUrl` (the page's path, its own fields and the
  team's) gives each option's `show_url`/`use_url` and the page's `TeamLinks` (`current`,
  `empty`, `without` per chip, `more`). Their CSS is the parts' own look (`team-slot`,
  `team-option`, `accent-panel` with `--accent`, `trial`). Icons: `statuses/`
  (StatusEffectIcons, by status kind; `service.team.icon_name` maps ours, e.g. DecreaseDefence
  → StatusReduceDefence).
- `just dump` (part of `just update`): the roytu fork of Il2CppDumper (github.com/roytu/Il2CppDumper
  at `~/repo/Il2CppDumper`, built with `dotnet build Il2CppDumper/Il2CppDumper.csproj -c Release
  -f net8.0 -p:RollForward=Major`, `RequireAnyKey: false` in the output's `config.json`:
  `just install` does all of it, `IL2CPP_DUMPER_DIR` moves the checkout) over the installed game
  into `data/dump/<game version>` (`dump.cs`, `script.json`), the version the code's own
  `StableManifestVersion` (the static data's lags until the game runs); skipped when a dump's
  `source.sha256` matches GameAssembly.dll + metadata. `just schema`'s input and where the RVAs to
  disassemble come from. The current dump: 11.95.0, metadata v39.
- `tools/extract_assets.py`: portraits, set icons and piece art from the game's Unity bundles
  (UnityPy) into `webui/static/assets/`.
- `optimiser/`: the model and solver (`tables`: the game's words and fixed tables; `account`:
  what the account holds, over them; `stats`, `damage`, `solve`, `assume`, `glyphs`, `labels`;
  `game_json`: the game's JSON named by a schema), `paths` (where the data lives) and `settings` (the store's rows as the model's
  types: the only model module besides `store` that touches the file).
- Battle (`optimiser/battle.py`; the champion page's Battle panel, `BattlePanel.vue` over the
  team finder's `TagPicker` and `RemoveChip`, which is a button when it has no `href`): buffs and
  a leader's aura assumed in a solve, as bonuses on base stats (`Request.battle`, added to the
  constant by `stats.constant_stats`, so every goal sees them; the "now" row too). Buffs by the
  game's status names (`IncreaseSpeed30`); ACC and RES ones flat (not yet read from the code).
  Fields `buff_<STAT>` (its strength) and `aura` (`Leader.key`, "<champion id>:<aura number>": a
  mythical has one per form). Only auras reaching the champion are offered (`auras_reaching`:
  affinity, faction, rarity; a Faction Wars one only to the leader's faction); the area is shown,
  not checked against the target.
- Rate goals (`optimiser/accuracy.py` `Lands`, `Resists`; the champion page's "Debuffs land" and
  "Resist debuffs" rows, `forms/request.py` `rank_LANDS`/`rank_RESISTS`, `min_landing`/
  `min_resisting` in %, against `enemy_res`/`enemy_acc`, which the target picker fills like
  `enemy_def`): a rate minimum is turned into the stat's at the form; ranked, the stat is capped
  where the rate stops rising and held within the slack of its best rate (`solve.held_floor`).
- Battle host (`host/`, Rust for Windows like the reader): **the game's own battle engine, run
  outside the game**, to sim any team against a fight's enemies (the story, checks and results so
  far: `docs/battle-host.md`). Plain Wine, a prefix of its own
  (`data/cache/host/prefix`), loads the installed GameAssembly.dll and starts il2cpp
  (`il2cpp_init` works without Unity), answers the three Unity calls the code makes (data
  folder, version, a buffer free: `unity`), runs two of the game's startup steps
  (`SharedModelLogger.Configure`, `MessagePack.Init`), loads the static data with the game's own
  cache loader from **a fresh copy** of the cache (`data/cache/host/LocalLow`: that loader deletes
  a cache it fails to load; it once emptied the real one), and sets the server's `BattleSettings`
  (the reader's `battle_settings`: turn limits, `WarmupBattleRandomCount`, …) as
  `SharedModelManager.GameParameters`. Objects pass as the game's JSON (`JsonMain`: its short
  keys, enums as numbers, values as raw `Fixed`). Commands:
  - `fight`: a `BattleSetup` in `BattleProcessor`, each turn the game's AI's choice
    (`EnemyTurnActionGenerator.GenerateNext`, either side, by the slots' skill settings)
    applied as the commands the game records (`GetDefaultSkill` is the A1, not auto's pick; the
    client's background mode needs client singletons). ~4 s a fight, deterministic; seed 0
    keeps the setup's own, and a captured fight replays exactly (checked: a co-op run's
    197,696,419 and every result-screen row).
  - `build`: the parts of a slot the game computes, by the shared model's own builders (the
    server's): gear (`ArtifactExtensions.ToArtifactSetups`, `GetArtifactSetBonuses`), Blessing
    (`BlessingSetup.From`), Academy (`AcademySetup.Create`, from the guardians), Great Hall
    (`BuildingSetup.FromVillageData`), relic stats (`RelicExtensions.ToRelicSetups`: partial).
  `optimiser/setups.py` writes the account as those objects (`request`: the reader's
  `value_fixed`/`glyph_fixed` and Mythical pieces' `rarity_glyph_fixed`/`glyph_rarity` keep
  values exact) and puts slots together (`assemble`): rank, level, empower, awakening, masteries;
  skills in the hero type's order, a copy skill at its source's level (`skills.json`
  `use_level_of`); the relic's skills at the level its level reaches, its stones' skills
  (`effect_sources.json` `relic_stones`), crit as a percentage; skill settings from a saved team,
  else the captured fight's (a saved team's settings are per wave: one sequence each). The enemy
  side is a stage's static data (`stage_setup`: its first formation, every wave, enemies' skills
  at level 1, awakening and boss flags from `enemies.json` placements' `awakened`, `hero_boss`,
  `main_boss`, the stage's modifiers; `KindId` Pve) or a captured setup's. Checked: the 907
  team built from the account replays that fight exactly; stage setups aren't checked against a
  captured one yet. `just sim <stage id | setup file> <ids> [seeds] [preset]` builds and fights;
  `just fight <setup> [seeds] [jobs]` (600 over 6 by default) fights a setup as is, the seeds split over `jobs` host
  processes (each its own static-data copy, `LocalLow-<job>`; the host's `fight` takes a first
  seed); the report lists the seeds that weren't cleared.
  `optimiser/fights.py` reads the results (`BattleResult` JSON: each `TurnStatistics` row
  counted once, in its producer's statistics; `DamageDealt` is in full past the boss's HP) and
  reports how often a fight is won and its turns (`BattleState.CurrentTurn`, everyone's, and
  `PlayerTurnCount`, the team's).
  Real fights are captured whole by `just capture`: it waits for a new one (a setup id, `z`,
  neither cached when it starts nor saved: the cache isn't always emptied between fights), saves
  its setup from the game's PlayerPrefs (`tools/capture_setup.py`: `BattleSetupCache_<user>` in
  the prefix's `user.reg`, base64 gzip JSON, read only) to `data/captures/setups`, waits for its
  result (`just results`, polled), then runs `just check-capture`: the replay on the fight's own
  seed against the game's record, outcome, turns and every result-screen row
  (`fights.differences`). `just results` is the reader's `--results` (`reader/src/battles.rs`):
  every live `BattleResult` (the last fight's, kept for its result screen; background runs')
  found by searching the heap for objects of that class (`Process::find_words`, committed
  private read-write regions, ~6 s; read only), validated (its setup's class, an outcome) and
  written to `data/captures/results/<setup id>.json` in the host's result shape, so
  `optimiser.fights` reads either. Checked against result screens: a co-op run and an Ice Golem
  Hard 10 run replay exactly; the screen's "Turns" is `CurrentTurn` (everyone's), not
  `PlayerTurnCount`. Not yet: changes to gear
  or relics before a sim.
- `optimiser/hit.py`: the reference model of a hit (`DamageCalculator`, `DamageContext`, the
  multiplier hooks) in the game's `Fixed` arithmetic (`optimiser/fixed.py`), bit for bit; the
  solver doesn't use it. `just test-game` (tests/test_game_code.py) checks it against the game's
  own code: `tools/game_emulator.py` runs GameAssembly.dll's methods in Unicorn on objects laid
  out from the dump (`tools/dump_types.py`, cached in data/cache), libil2cpp's entry points found
  from known call sites; needs the installed game's dump and the `emulate` group. What it covers
  and how: `docs/game-model.md`, Damage.
- `optimiser/store.py`: user state the snapshot doesn't hold, in SQLite at `data/state/optimiser.sqlite`
  (stdlib `sqlite3`): champion locks 1–5, set on the champion list, and reserve rules
  (`optimiser/reserve.py`, by `rule_key`: `Tagged(marker)` what champions with a tag wear,
  `GlobalPresets` every global gear preset's pieces even unworn, `Team(preset id)` what a saved
  team wears; what they reserve comes from each snapshot; edited on the Config page, `/config`).
  A solve's `GearFilter`
  says what gear it may not take, each part toggled on its own on the champion page: each reserve
  rule (`exclude_<rule key>`, on by default), champions locked above a level, anything other
  champions wear. Taken pieces note what reserves them. The champion's own gear is always
  allowed. Locks are kept for now, to compare.
  Also what solves assume (account-wide, on the same Config page, once `/assumptions`;
  `optimiser/assume.py`): flags for
  the champion at their rank's top level, gear at +16 (main stat only) and ascended gear fully
  ascended (`planned_*` fields; `data/game/gear.json` tables, checked exact against every piece),
  and glyphs to assume (a grade per kind): `optimiser/glyphs.py` gives solves a copy of the account whose substats of those kinds carry the grade's top roll
  (`StatLine.planned_glyph`), capped below 6* at the best glyph of the piece's rank, where it
  beats the real glyph; current stats use the real gear. Only stats the request wants more of
  are glyphed (`solve.directions` > 0: minimums, ranked stats, the damage skill's stats + C.DMG).
  Also each champion's run history: the submitted form and the outcome view
  (`dataclasses.asdict` JSON, rebuilt by `service.runs.revive`; a run whose shape no longer fits
  shows only its inputs).
- Accessories (`/accessories`, tabs in the workflow's order: Swaps · Roll · Rework · Clean up,
  then Weights; `optimiser/accessories/`, which doesn't use the solver). Only unequipped gear takes
  inventory space (2200 for accessories); overflow waits in the mailbox (the inbox's
  pieces, `Account.mailbox`).
  - `roles.py`: champion types (per-stat weights, the main stats that suit them, damage or
    support, for any faction or one) and set fits (`SetTable`: per set, its value and the
    types it doesn't target, which count at `off_target` of their score, 0.5 by default; the
    store's `set_fits`, seeded once from the old set roles and meta tiers; unknown sets and new
    types fit everywhere at value 1; a copied type keeps its original's). A set targeting no
    damage type still keeps one C.DMG amulet, counted in full. Clean-up rules that read a set's
    kind read what it targets (`SetTable.kinds`). The types are the user's,
    edited on the Weights tab (add, copy, delete), kept in the store's `champion_types` (JSON
    per row, keyed by row id; `settings.read_champion_types`). They're seeded once, on first
    read, with `STANDARD_TYPES` (ATK/HP/DEF damage, bomber/poisoner, support) and the roster's
    faction types (`scaling.seed_types`); a seed already done never reruns.
  - `scaling.py`: the seed's faction types, from the 6★ roster: each champion's pull per stat from its
    formulas (damage hits and bombs; for Support-role champions heals, shields, revives:
    `skills.json` `scaling`), each effect counting its shape. Mixed scalers (Rotos, Fellhound)
    and supports healing off ATK (Kurosa) get a type for their faction only. Each mythical
    form counts as a champion of its own (`Tables.hero_forms`). Exceptions go in
    `scaling.OVERRIDES` (`Skip` / `Weigh`, by champion name and form; they shape the seed
    and the report only, not the stored types); the
    `champion-exceptions` skill finds candidates with `just exceptions`
    (`optimiser/accessories/scaling_report.py`).
  - `potential.py`: every way a piece can turn out (upgrades at +4/8/12/16 add a substat until
    four, then roll one; a rework keeps each line's roll count, set and faction and re-picks
    main stat and substats; once only: `RerollsCount`), scored in average 6★ rolls, quantile 75.
    Each substat counts the best glyph its rank can take, never the glyph it has: having the
    stat is what makes a piece glyphable. Each type's score is weighed by its set fit.
  - `rules.py`: the user's rules (`Rules`, the store's `accessory_rule:<field>` numbers, the
    code's defaults until set; each set's `SetRules`, keep and RES/SPD banners, in its set fit's
    record, seeded on first read): the keep rules' switches and numbers, good share, shortage
    factors, surplus, swap and rework margins. Edited on the Weights tab (Rules; the set grid's
    Keep and RES/SPD rows). Scoring doesn't read them: changing one rescores nothing.
  - `assess.py`: each piece's value: max(+16, rework) potential × shortage factor (good
    pieces on its set/faction/slot: ×1.15 none … ×0.9 three+, `Rules`) × the set's value (the set fits;
    seeded from `roles.SET_TIERS`: Swift Parry 1.5; Mercurial, Merciless 1.3; Feral, Slayer,
    Pinpoint 1.15; set-less 0.6; `SET_NEEDS`: the crit sets only target types weighing C.DMG,
    Pinpoint those weighing ACC).
  - `cleanup.py`: inventory + mailbox planned together; the lowest values go until
    `target_free` spaces are left (sold, or left unclaimed). Special variants
    (`VariantId` "Corrupted": unusual stats, a border) are left alone everywhere. Never dropped: protected pieces, reserved pieces (swaps may still move them),
    banners with SPD rolled 3+, each set's best RES banners with SPD (2 for a set targeting
    support types, else 1: RES breakpoints), good potential (slot's top quarter), each faction's Faction
    Wars reserve, 6★ damage-set amulets not yet reworked (may rework to C.DMG). Group quotas
    (each set's keep: seeded 2, 1 for low-value sets) make the surplus go first. Each keep rule
    but protected, reserved and special can be switched off (`cleanup.SWITCHED`). Swaps (own tab, by champion): a loose
    piece clearly better than one an unlocked champion wears in the same group is planned as
    equipped (Equip button; the piece coming off may then be sold). Lock champions whose gear must stay.
  - `enhance.py`: roll to +12 (cheap, informative), to +16 (only good pieces), rework lists.
- Nav (`service/layout.py` `nav_sections`, drawn by `layouts/AppLayout.vue`): Optimiser,
  Accessories, Teams, Info; a section with several pages shows them as tabs in a band under the
  bar (`subbar`), unless the page has its own (`composables/subnav.ts`: `usePageSubnav` hands
  the layout its tabs as data, which it draws like its own; Accessories' steps). Optimiser: the
  champion list, the champion last solved for (`store.latest_champion`), Config; Teams: the finder
  (the Chimera's trials too) and Gear; Info: Faction Wars, Events, Empower (`/empower`),
  Masteries, Skill books.
- Info page (`/info`, `webui/service/info.py`): the account's progress from the snapshot.
  Faction Wars Hard: per crypt, stages short of their stars and the battle quests they may still
  need (`enemies.json` stages' `quests`, texts from `BattleQuestData`; a stage one star short is
  missing one of the two after "Beat Stage", shown as its challenge "or 5 Champions, no losses").
- Events page (`/events`, `optimiser/events.py`, `webui/service/events.py`, `pages/Events.vue`):
  the events and tournaments the game held at the last sync, running, coming up, and ended with
  prizes still to claim (each card's header, with the time left, folds the rest: open for those
  running), each with the account's points and place over its milestones, and what earns
  points (an action's rules as a table per field set, a grid when they vary along two; what all
  share said once). Titles and points' names are the game's (`EventTexts`: the settings' `TitleId` and
  `PointsNameId`, looked up in the snapshot's texts); Plarium's own name ("Fuse 10910 Ice Golem (3d), 26-11-2026") is the title's
  tooltip, and gives the fusion's champion. Milestones may be per bracket of levels: the account's is the
  one its standing names (0-based), else the one holding the level its other brackets agree on
  (`events.account_levels`). An event scoring summons (Champion Chase) shows, under its
  milestones, the shards reaching one takes (`ShardPlan.vue`, `webui/service/summons.py` over
  `optimiser/summons.py`): the milestone clicked in its table (else the next not reached),
  less champions counted by hand (M, VL, L, VE, E: `summons.MANUAL`, their points from the
  event's summon table); a new shortfall asks `/events/{id}/shards?short=` (`shard_rows`), the
  page bringing only its first target's. Per shard type, one type alone, at
  today's odds (a running boost's), typically and nine times in ten, from `TRIALS` simulated
  openings with mercy (the extra chance taken from the commonest rarity) from none built up;
  a type with no mercy (Mystery) worked out instead. Points per rarity are the event's summon
  rules, averaged over the affinities the shard summons. An event scoring level-ups (Champion
  Training) shows the champions to brew instead (`BrewPlan.vue`, `webui/service/training.py` over
  `optimiser/levelling.py`): per grade (3★–5★), a new champion brewed to half its top level with
  brews of its own affinity (2, 4, 7), what that earns, and how many of them the milestone takes. A Turn
  Attack (`TurnAttackParameters`) shows the runs instead (`FightPlan.vue`, `webui/service/fights.py`):
  a stage and the turns a run takes, what one earns and how many the milestone takes; so does an
  event scoring the gear runs drop (`Battle_DungeonReward`: Ice Golem, Dragon, Fire Knight), a
  run's average from the stage's drop odds (`optimiser/loot.py`: each rule a piece matches adds
  its points, rank and rarity drawn apart; rules on what the odds don't give, a piece's set or
  slot, earn nothing; accessories aren't read). A Gear Enhancement (`Artifact_Upgrade`) shows the
  pieces instead (`UpgradePlan.vue`, `webui/service/upgrades.py`): new 5★ or 6★ pieces taken
  from +0 to +12, each level's points for its rank summed, and how many of one rank the
  milestone takes. Each card's plans come from one hook,
  `webui/service/plans.py` `event_plans` (`EventCard.plans`, each plan's `kind` telling the page
  which component draws it, in the shared `PlanPanel.vue` frame; big numbers are `Stat.vue`), over
  `optimiser/event_tables.py` `PlanTables` (summons, levelling, loot). Every plan reads the rules
  through `events.rule_points` / `holds`: a rule holds when each condition does for the facts
  given (a value, one of a list, a stage range), and every rule that holds adds its points. The server
  scores turns, not the client; `TurnPoints.points` is round(S × X × turns^Y) held between its
  min and max, read off two real fights (Sand Devil 25: 44 turns 43 points, 22 turns 48). A tournament ends `BracketDuration` after its start, a day past its
  stored `End` (`events.event_end`), as the game's timer (the tournaments web view's) shows and
  points keep counting; `End` + `RewardDuration` gives the same time today. Co-op events' points are the team's damage, and their prizes aren't
  read.
- Skill books page (`/books`, `webui/service/books.py`): the champions with a skill below
  its top, as at the last sync, the champion filter bar above them narrowing it by stars
  too (`service.finder`'s `matches` and `FilterChoices`). `forms.books`'s `DEFAULTS` start
  it on 6★ Legendaries, and the bar sends its rarity and stars even when they're "any"
  (`Any`, `any`), so one missing from the URL means nobody has chosen it yet. A skill's
  level is 1 + the books spent on it (`Champion.skill_levels`, read for damage and kits),
  and the game defines each skill's books (`Skill.books`, from `SkillLevelBonuses`), so
  its top is one past how many it has — a skill with none (some passives) can't be booked
  and counts as there. Those one book from done, then the rest by fewest books short. Each
  skill is named by where it sits in its form's skill list (A1, A2 …, P1, P2 …; its name
  only in the badge's tooltip), shown how far below its top it is with the books it hasn't
  had on a line apiece under it (`Skill.books` from `SkillLevelBonuses`: damage, effect
  chance, a turn of cooldown, HP, shields, ignore RES). A mythical's two forms take books
  of their own (`forms_short` over `hero_forms`; only mythicals have a second, and the
  reader doesn't say which form the champion is in), so one short in both shows a labelled
  block per form on its card. Slots and tops are `service.skills` (`form_skills`), which the
  champion page's Skills card (under the profile: a tab per skill of the picked form, its books as
  "1/3", its cooldown after the books it's had (`Skill.cooldown_at`) and the game's text,
  `skills.json` `description`) shares.
- Masteries page (`/masteries`, `webui/service/masteries.py`): the 6★ champions with no mastery
  in a tree's last row (Helmsmasher's), split into those holding enough scrolls to reach it and
  those still to farm for (fewest Divine short first). Per kind (Divine, Advanced, Basic: the
  game's Gold, Silver, Bronze): had (held + spent on masteries) against needed (spent + a
  mastery in each row below their furthest: 550 Divine from one row 5, 750 from two). Rows and
  prices from `bonuses.json` `mastery_types` (`Tables.mastery_types`: each mastery's depth under
  `MasteryTypes`' parents and its `Price`; ids read `500<tree><row><column>`).
- Champion list and finder, one list (`webui/service/finder.py`: `find_champions`,
  `lock_champion`; `forms/finder.py`). Its filter (`matches`) and bar's options (`FilterChoices`)
  are the skill books page's too; `ChampionFilters.vue` takes those, and `watchFilters` a page
  keeping its own filters (`keep: null`) skips remembering them in `finder-filters`. The list
  (`/`, `pages/Champions.vue`, `ChampionFilters`, `ChampionCard`, `LockPicker`): the filters
  (`q`, `rarity`, `faction`, `grade`) ride in the URL and a change reloads only its `finder`
  prop; each champion carries their lock (`/champions/{id}/lock` saves it and goes back).
  The finder dialog (`components/ChampionFinder.vue`, `/finder` as JSON): its cards are picks, announced
  (`picked`) for the page to act on (the champion page's Switch champion visits their
  optimiser; `TeamSlots` puts the pick's id, `views.slot_value`, in a slot: a slot field
  is an id, still read as "… #id" or part of a name; trailing open slots are left out of URLs); a
  page holds it to what a stage admits with `only`/`onlyLabel` (`service.finder.OnlyView`, the
  dialog's `only_*` fields). Enter takes the first. The
  filters (not the name) are remembered in the browser (`finder-filters` in localStorage),
  shared by the list and the dialog.
- Target picker (`webui/service/targets.py`, `forms/targets.py`, `components/TargetPicker.vue`,
  route `/targets`): a reusable component, top of the champion page, Team gear and the team
  finder (its stage). Zone
  (`ZONES`: Dungeons, Clan Boss from its tiers × affinities, the Chimera from its tiers ×
  rotations (the forms' affinities), Faction Wars, Hydra, Doom Tower,
  Grim Forest, Cursed City, co-op Demon Lord, Campaign) → group (region; shared names get what
  tells their ids apart) → difficulty → stage → wave (the last by default; its select at the
  right of the enemy's name), then one of its enemies (boss, else most HP). Each change asks
  `/targets` for the view as JSON (`changed`: lower levels reset) and emits `picked`: the champion
  page sets `enemy_def` and keeps the pick as `target` ("<stage>:<wave>:<slot>", plus `base=stage`
  where a page needs the stage on its own — Team gear and the team finder), saved with runs, whose
  picker the server draws back from it. The panel dims (`detached`) when `enemy_def` no longer
  matches it.
- Inertia (Vue 3 + TypeScript): every page is a Vue page. `webui/inertia.py` is the server
  side of Inertia v3's protocol, our own (`respond`: the shell `templates/inertia.html`, the
  only Jinja left, with the page in its `<script data-page>` on a first load, JSON on the
  client's visits; partial reloads; props may be callables, evaluated only when sent; 409 on a
  stale build; `redirect`/`back`, 303). `responses.inertia_page` adds what every page gets (`layout`:
  `service/layout.py`'s nav and sync age; `errors`). A form that fails goes `back` with its
  errors (`responses.back_with`: a one-shot cookie, `inertia.ERRORS_COOKIE`, shown in the layout's
  alert). A component's own requests get JSON, not a page: the finder dialog (`/finder`), the
  target picker (`/targets`), the game commands (equip, preview, sync, sell: `responses.sent`,
  `{error}`) and settings saved in place without a reload (accessory weights and set fits:
  `responses.saved`, as rescoring is slow); `composables/send.ts` posts them. Settings that change
  what a page shows post with `composables/save.ts` and reload its `page` prop. The champion
  page: `?run=<id>` names the run shown (`champions.shown_run`: else the latest), its form
  restored from it; history picks reload `run` and `picker` alone; a solve redirects to its new
  run; nothing about runs is kept in the browser. The front end is `webui/frontend/` (Vite;
  `src/app.ts`, `layouts/AppLayout.vue`, `pages/<Component>.vue`, `components/`, `composables/`),
  built into `webui/static/dist/`
  (gitignored). A component's own look is its `<style scoped>` (moved out of `app.css`, so
  deleting a component deletes its styles); the shared vocabulary stays global (below). A rule
  reaching inside a child component uses `:deep()`, and only in a flat rule: nested, Vue
  compiles it wrong (`.a { :deep(.b) }` becomes `.a [data-v] .b`, matching nothing). A child's
  root element is reached without it, and slot content is styled by the component that writes
  it. Props are typed: `tools/gen_ts_types.py` writes `src/types/generated/<python
  module>.ts` (gitignored) from `webui.service`'s dataclasses and those they reach (shared
  shapes in `src/types/views.ts`), and `vue-tsc` checks the pages against them
  (`just frontend-check`, in `just check`).
- `webui/`: FastAPI + Inertia + Vue, our own CSS (no framework). `service/` is framework-free
  (frozen dataclass view models, sent to the pages as props), a module per page
  (`champions`, `results`, `runs`, `accessories`, `assumptions`) over `current` (paths, the
  cached account, locks), `views` (champion rows, piece names and art) and `scores` (accessory
  potentials kept in `data/cache/potentials.pickle` by piece state, per scorer and scoring
  code, so only changed pieces are rescored); `forms/` is the form boundary (forms post form data
  (`forceFormData`): `request` the solve form and build buttons, `settings` those that change the
  store, `chimera`, `common` `FormErrors`); `result.py` is the `Err`/`Result` that `extractor.py` and
  `reader.py` return; only `app.py`, `routes/` (a router per area), `responses.py`, `inertia.py`
  and the shell know about HTTP/HTML.
  Three stylesheets, in order. `static/theme.css`: the tokens, one theme, Vault (dark only),
  colours named by Material 3's roles (`--primary`/`--on-primary`, `--surface` then
  `--surface-container-lowest`…`-high` for depth, `--on-surface`, `--on-surface-variant` for
  muted, `--outline`/`--outline-variant`), plus `--heading`, `--stat-up/mid/down`, `--debuff`/`--buff` (a tag's side: always red/blue), the game's
  colours (rarity, forms, art), fonts and one scale each for sizes: `--text-2xs`…`-4xl`,
  `--space-3xs`…`-4xl`, `--radius-s`/`--radius`/`-l`/`-pill`. stylelint (`declaration-property-
  value-disallowed-list`) keeps rem literals out of spacing, font sizes and radii, raw colours
  out of everything but custom properties, and bare durations out of transitions: use a token
  (em stays for sizes relative to their context, px for hairlines). `static/base.css`: the
  elements themselves (reset; prose's flow margins, zero-specificity; tables headed in caps;
  buttons filled brass, `quiet` for secondary, `small` inside rows and cards, `icon` (a bare
  × or ✕, red on hover), `dashed` (adds another); fields (`small`; numbers bold and centred;
  `input.bare`: a number typed into its cell; `label.inline` beside its field), checkboxes,
  switches; a cell's `small` muted;
  cards with a rim, no shadow; dialogs; nav) and Every Layout's primitives (`stack` and
  `cluster` by gap, `with-sidebar`, `switcher`, `grid`), parameters set inline (`style="--space:
  var(--space-s); --align: center"`; also `--justify`, `--min`, `--repeat`), registered
  non-inheriting (`@property`) so they stop at the primitive; a list laid out by one is
  unstyled; `push` sends a child to the far end (`margin-*-start: auto`), `grow` lets a field
  take its share (`--basis`, inherited), `clamp` cuts text to `--lines`. Lay pages out with
  these, not a class per container; `.joined` joins a field and its button. Spacing is the
  parent's job (`gap`, the primitives), with logical properties. `static/app.css`: the
  shared components (what pages use raw, or several components share: tile frames' art, the
  piece card's box, the listed champion's base). The look (◆ section titles) follows the Stitch
  design system the user supplied,
  but keeps Alegreya (headings) and Alegreya Sans (text), the user's choice over the spec's
  fonts. Colour by tone: `good`/`up`, `bad`/`down`, `mid`, `info` set `--tone` (registered,
  non-inheriting); text takes it as its colour, and a `badge`, `status`, `meter` or `note`
  as theirs, so a variant is one class, not a rule per component. The shared components:
  `panel`/`panel-head`, `well`, `table-well`, `caps`, `note` (small, muted), `figure` (a big
  number), `badge` (`quiet`: outlined; scores and difficulty too), `alert`, `chip` (`on`),
  `status` (`met`/`missing`), `segmented` (`small`; checkboxes for several) and `page-tabs`
  (the same look for links), `filter-bar` (the page filters its items),
  `slot` (`empty`), `stat-tiles` (`edit`), `switch-rows`, `page-head`, `tally`, `cta`,
  `danger` (selling), `champion` (`ChampionCard`: every listed champion, tile and name as one
  link, its slot's extras under it; `card`, `small`, `suggested`; its `tile`, `ChampionTile`,
  carries the rarity's crest, scaled by
  `--tile-width`, and draws any view with a name, rarity and portrait: the target picker's
  enemies have no level or stars) in a `champion-grid`, `portrait` (round, rimmed in the
  rarity: who brings a need, who wears a piece), `stars` (`Stars`: the game's star art,
  plain ★, or so many out of a total), `page-head` (`PageHead`: its `lede` and `aside`
  slots) and `tally`, `gear-pair` (`GearCard` `candidate`/`worn` over the optimiser's
  `PieceCard`). A piece is one view everywhere, `service.results.PieceView`
  (`piece_view(artifact, account, champion=None)`: through a champion's eyes, or nobody's);
  an accessory's `AccessoryRow` is that plus its scores. Drawn as a card (`PieceCard`) or a
  list row's cells (`PieceCells`), both with `PieceArt`, `meter`; in tables, `num` cells. Heads' own margins are
  zero-specificity (`:where`), so a primitive's gap wins. Build pages from those, the
  primitives and the tokens; `/palette` shows them all.

## Commands

Use the `justfile` (`just` lists every recipe). It is the only place that knows machine paths
(`.env` overrides its defaults) and passes them to the tools as arguments.

```
just install          # a fresh checkout: paths, Il2CppDumper, the Rust target, mitmproxy's CA, then update
just update           # after a pull, game update (launch it once first) or HH update: deps, HH patch,
                      # dump (when the code changed), reader layout + build, schema, static, assets, front end
just read             # the account, from the running game's memory (read-only)
just watch            # keep reading it while the game runs, when it changes (Ctrl-C stops it)
just capture          # capture the next fight whole (setup, then its result) and check its replay
just results          # the finished fights the game still holds, from its memory (read-only)
just check-capture <setup> # a captured fight's replay against the game's record of it
just fight <setup> 300 6 # the game's own battle engine on a setup, on auto, per seed (6 processes at once): clears, turns, rows
just sim <stage> <ids> 600 [preset] # any champions, as they are, against a stage (or a captured fight)
just proxy            # the HH extractor's game commands: equip, preview, sell (extractor + game running)
just web              # http://127.0.0.1:8000 (web-restart, web-stop); needs frontend-build
just web-dev          # the same with Vite's dev server (Vue pages reload as you edit)
just frontend-build   # prop types + Vite build into webui/static/dist (part of update)
just seed [--reset]   # list the accessory seeds (types, set fits); --reset backs up the store, reseeds both
just check            # black + ruff over all Python, the house style checker, stylelint, then Prettier + vue-tsc over the front end
just css-fix          # Prettier, then stylelint's fixes (property order, quotes), over webui/static/*.css
uv run --group dev pytest   # tests/ (not part of just check)
just test-game        # optimiser/hit.py against the game's own code, emulated (~40 s)
```

The steps install and update run (`tools`, `ca`, `hh-patch`, `dump`, `reader-layout`, `reader`,
`schema`, `static`, `assets`) are `[private]`: `just --list` hides them, `just <name>` still runs one.

The web server reloads itself when Python under `optimiser/` or `webui/` changes
(watchfiles; `--no-reload` turns it off); static files are read fresh anyway. Vue pages need
`just frontend-build` after a change, or `just web-dev` (Vite's dev server, hot reload). Stop it by port (`ss -ltnp 'sport = :8000'`), not `pkill -f` with a pattern
that also matches your own shell command.

## Conventions

Follow `~/repo/python-style` (rules, examples, checker): module docstring maps that name what
the module defines, workflow functions, frozen dataclasses, narrowable unions + `match`
over flags, `Result`-style returns for reportable failures, blank lines around blocks. ruff
and black at line length 100, over `optimiser webui capture tools` (`just check`). `tools/` is a
package of click commands run as `uv run python -m tools.<name>`: paths come in as arguments,
never hard-coded, and the project's own paths from `optimiser.paths`. `capture/hh_capture.py`
runs inside mitmproxy (`uv run --group capture`), so it stays standalone.
CSS: Prettier formats it (one declaration a line, width 100, `.prettierrc.json`) and stylelint
checks it (`just css`, in `just check`; `just css-fix` fixes both). `stylelint.config.mjs`: the
standard config, properties in the clean-order preset's order (stylelint-order), and native
nesting at most 3 deep (`&` for the same element: `&:hover`, `&.on`; bare for descendants).
Nest under a single selector, not a list (`&` would act as `:is()` and raise specificity).
Vue/TypeScript: Prettier formats `webui/frontend` too (`just frontend-check`); a component
starts with a comment saying what it draws, as a module's docstring would; pages get their
data as props typed from the views, never by fetching it themselves (a component's own
request, like the finder's, is the exception). `package.json` holds the front end and that
tooling (`npm ci`, part of `just update`).
Shell: `grep` is aliased to ugrep, so use `/usr/bin/grep`.

## Game model

`docs/game-model.md` — how the game computes it, read off its code and checked against it:

- **Stat model:** stat = base + Great Hall + arena + awakening + empower + masteries + relics +
  gear; percentages apply to base except crit; rank/level scaling in Q32.32 `Fixed`; ascension,
  empowerment, glyphs, main stats and sets.
- **Damage:** a hit's steps (phases) and who hooks each, the formula's factors (affinity, hit
  type, DEF, status reductions, stat modifiers, roll), how modifiers combine, and reflected,
  shared, DoT and bomb damage.
- **Resist:** the chance from RES − ACC: 3 % floor, 97 % cap, and the two breakpoints.
- **Solver:** the MILP in HiGHS: its variables, lexicographic ranking, damage ranked by log tangents.
- **Raider oracle:** calling game code from an injected DLL, to check formulas against the game.
- **Assets:** how the extracted portraits, art, icons and banners are named.
