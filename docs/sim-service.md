# Sim service: a hosted battle sim

2026-11-28

## Summary

The battle sim is the part of this project with no equivalent elsewhere, so it's the product:
a hosted sim that runs any team against any stage, paid for with tokens. Gear optimising is a
well-trodden path; some info pages may be free, as community value.

- **Engine:** our own Rust reimplementation of the battle engine, run on our servers. The
  game's own engine, hosted under Wine (`docs/battle-host.md`), stays on the developer's machine
  as the oracle we check it against, turn by turn.
- **Account:** the reader, run on the player's machine as a server on 127.0.0.1, read by our
  static site in their browser.
- **Game data:** comes only from the player's own install. Our servers handle it during a
  request and never keep it.
- **Not in it:** anything of HH's (the extractor's game commands: equip, preview, sell), and
  anything of Plarium's code.

We'll talk to Plarium about it too; this design is meant to need as little from them as
possible. None of this is legal advice.

## Principles

1. **No game code on our servers.** The hosted engine is our own code. It interprets the game's
   data; it contains none of the game's code, tables or text.
2. **Game data comes from the player's install, and isn't kept.** The reader decodes it on the
   player's machine. A sim request carries only what that fight needs; the server uses it for
   that request and discards it. Nothing of Plarium's is stored, cached or served by us: not
   data, not text, not art.
3. **The static site serves only our code.** Free pages ask the local reader for the data they
   need and compute in the browser.
4. **The reader never talks to the internet.** It reads the game and answers on 127.0.0.1;
   the browser sends everything that goes to our server. One place for login and tokens, and a
   simple trust story for a tool that reads game memory.
5. **Exact or not at all.** The engine matches the game's to the bit, or says it can't: an
   unimplemented effect or a missing piece of data returns `Unsupported` or `MissingData`,
   never a guess. What's offered for sale is what's covered.
6. **The game's engine is the specification.** Every behaviour is checked against the host on a
   corpus of fights, and re-checked after every game update.

## Architecture

```
 PLAYER'S PC (Windows)                                       OUR SERVER
┌────────────────────────────┐   127.0.0.1   ┌───────────┐  HTTPS  ┌───────────────────────────┐
│ reader                     │◄─────────────►│ browser:  │────────►│ sim API (stateless)       │
│  memory: account, teams,   │  CORS, paired │ static    │  login, │  request: account slice + │
│   battle_settings, …       │  token, SSE   │ site      │  tokens │   data slice + stage +    │
│  disk: static-data cache   │               │  free     │◄────────│   settings + seeds        │
│   → typed data, slices     │               │  pages in │ summary │  sim-setup → sim-core     │
└────────────────────────────┘               │  browser  │         │  → summary; data dropped  │
                                             └───────────┘         └───────────────────────────┘

 DEVELOPER'S MACHINE (private)
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ full static data · Wine host (the game's engine, + trace) · corpus · differ · coverage report │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

### The reader, as a local server

Today's `just watch` already waits for the game and notices when the account changes; serve
mode answers requests instead of writing files.

```
reader serve   (binds 127.0.0.1 only)
  GET  /status          game running? game version, layout version, paired?
  POST /pair            the code the reader shows → a token
  GET  /snapshot        the account, as today's snapshot.json
  GET  /events          as today's events.json
  POST /slice           a fight's description → the static data it needs (below)
  GET  /data/<part>     what a free page needs (event rules, mastery prices, …)
  GET  /stream          SSE: "snapshot changed", "events changed"
```

- **Browser rules.** An HTTPS page may call `http://127.0.0.1` (a secure context in Chrome,
  Edge and Firefox). The reader answers CORS for our origin only, never `*`, and sends
  `Access-Control-Allow-Private-Network: true` on preflights. Chrome's Local Network Access asks
  the player once to allow it: onboarding explains that prompt.
- **Any site can try the port**, so the reader binds 127.0.0.1 only, checks `Host` (against
  DNS rebinding) and `Origin` on every request, needs the pairing token, and is read-only: no
  commands, no paths.
- **Starting it:** the installer registers a URL protocol (`raidsim://start`), so the site can
  start the reader when `/status` doesn't answer.
- **Fallback:** where a browser refuses local access, the reader writes an export file the
  player uploads through the site.
- **Static data:** the reader decodes the game's static-data cache from disk (`just static`'s
  MessagePack + LZ4 work, ported to Rust) into the typed model of `sim-data`.

### The data slice

A fight needs well under 1 % of the static data: five champions' skills (about 40, more with
mythical forms), the stage's enemies' (about 40), the sets and relics worn, the stage and the
server's battle settings. From today's exports (`skills.json` about 1 KB a skill) that's
roughly 150 KB of JSON, 20–30 KB compressed.

The hard part is completeness: data points at other data. The slice is everything a fight can
reach from its champions, enemies and stage: copy skills (`use_level_of`), mythical forms,
Hydra head pools, the Chimera's forms and trial skills, summons and transforms, relics' stones,
auras, stage and slot modifiers, and the effects and statuses skills name.

- `sim-data` computes the slice. The same crate runs in the reader and on the server, so the two
  can't disagree about what a fight needs.
- The engine refuses a reference that isn't in the slice (`MissingData`).
- The harness runs every corpus fight from its slice alone, so a gap shows up in testing, not
  in a sim someone paid for.
- The slice is our typed model, not the game's records: knowledge of the game's schema lives in
  one versioned crate. A schema change means a reader update, which a game update needs anyway
  for the memory layout.

### A sim request

- **In:** the game version and slice format version; the account slice (the team's champions,
  their gear, relics, Blessings, masteries; Great Hall, Academy; `battle_settings`; the
  Chimera's HP left); the data slice; the stage; skill settings per wave; the number of seeds.
- **The server builds the fight** (`sim-setup`, checked once against the host's `build`) rather
  than taking a ready-made `BattleSetup`, so no client can send a fight the game couldn't
  produce.
- **Out:** a summary, built as fights finish: clears and how the rest ended, turns, damage,
  the Chimera's trials, each champion's rows, the seeds that weren't cleared. Not the full
  results (100 Hydra fights' are about 1.8 GB). A seed is rerun, deterministically, for anyone
  who wants to see one fight.
- **Limits and price:** seeds and turns capped per request; tokens by fights run, weighted by
  the turn limit (a Hydra fight costs far more than a dungeon run).
- **Kept:** the summary and ids, keyed by a hash of the whole request and the engine version.
  The same request again is free and instant, and a doctored request can't hand its result to
  anyone else.
- **Refused:** a game version or slice format the engine doesn't support yet, with a message
  that says so.

A player editing their own slice only gets a wrong sim for themselves, and pays for it.

### The engine

```
sim/ (cargo workspace; native for the server and harness, wasm32 possible later)
  sim-fixed    Q32.32 Fixed, bit-exact                      ← optimiser/fixed.py
  sim-rng      the game's RNG, seeding and warmup draws     ← the dump, checked on the host
  sim-data     typed static data, decoding, slices          ← tools/static_*, data/game
  sim-setup    account slice → BattleSetup                  ← host build, optimiser/setups.py
  sim-core     the battle                                   ← the dump; the host's traces
  sim-result   BattleResult, TurnStatistics, trials, summary ← optimiser/fights.py
  sim-cli      fights a setup across seeds (rayon); the harness's runner
  sim-api      the hosted service
```

`sim-core` reads and writes the same shapes as the host: a `BattleSetup` in, a `BattleResult`
out, as the game's JSON. Everything that reads the host's results today (`optimiser/fights.py`,
the Sim page) reads the engine's unchanged, and comparing the two is a diff.

Inside `sim-core`:

- **Turn loop:** turn meters, who moves, the turn limits (`mt`, `bt`, an area's own).
- **AI:** each turn's skill choice by the slot's skill settings (priorities, openers), as
  `EnemyTurnActionGenerator.GenerateNext` makes it, for both sides. One different choice changes
  the rest of the fight, so this is matched exactly.
- **Skill executor:** an interpreter from effect kind to handler. Effects are data; the
  handlers are the engine.
- **Event bus:** turn start and end, before and after a hit, a status placed, a death, a revive.
  Passives, sets, relics, auras and boss mechanics subscribe to it.
- **Conditions:** the game's effect and target conditions, evaluated.
- **Damage:** `optimiser/hit.py`'s pipeline, which `just test-game` already checks against the
  game's code.
- **Statuses:** buffs, debuffs, shields, damage over time, Hydra heads, Chimera trials.
- **Determinism:** `Fixed` everywhere, no floats; ordered collections only (`Vec`, `BTreeMap`),
  in the game's own tie-break order.

### Verification

```
corpus ─► host (the game's engine, trace on) ─► reference traces + results ─┐
       └► sim-core (the same trace format) ─────────────────────────────────┴► differ
                                                                               │
                         first divergent action, with both states at that point ◄┘
                         coverage: effect kinds × champions: matches / diverges / unsupported
```

- **Corpus:** captured fights (`just capture`: real results), stage setups × saved teams, and
  generated fights (random rosters × stages × seeds). Reference results are made on the host
  once per game version and kept on the developer's machine.
- **Trace:** each action's actor, skill, targets, hits, every hero's HP and turn meter, the
  statuses placed and removed, and the RNG draw count. A wrong turn-meter tick changes the rest
  of a fight, so the first divergence is what matters, and an extra or missing draw is the most
  likely way to drift.
- **Coverage report:** which effect kinds, champions and stages match, diverge or aren't
  supported. What's sold is what matches.

### After a game update

1. `just update`: a new dump, reader layout, schema and static data.
2. Rerun the corpus on the host, then diff the engine against it.
3. Fix what changed in the engine and in `sim-data`'s decoding.
4. Release the reader (layout, decoding) and the engine for the new game version. Until then, the
   server refuses requests for it, with a message.

## Free and paid

| | Runs | Cost to us |
| --- | --- | --- |
| Info pages (Faction Wars, events, masteries, skill books, …) | browser, from the reader | none |
| Sim | our server | compute, paid for with tokens |
| Gear optimiser | undecided (browser with HiGHS in WASM, or not offered) | none if in the browser |

New accounts get some free tokens.

## Relation to the open-source release plan

`docs/release-plan.md` planned shipping the whole app to players. This plan replaces it as the
direction: the web UI becomes a static site, and no Python ships. Parts of it carry over: the
maintainer/player split, layouts published after each game update, the reader built natively on
Windows in CI, code signing against antivirus flags, and the rule that Plarium's tables and art
are never redistributed.

## Build steps

Each phase ends with something checked against the host.

### 1. The harness

- [ ] A trace mode in the host: the trace above, as JSON lines, per fight.
- [ ] The corpus: today's captured setups, stage setups × saved teams, a generator for random
  ones; reference traces and results per game version.
- [ ] The differ (`just diff-sim <setup> [seeds]`): the first divergent action, both states.
- [ ] A coverage report over the corpus.

### 2. Foundations

- [ ] The `sim/` workspace.
- [ ] `sim-fixed`, against `optimiser/fixed.py`'s tests and `just test-game`'s cases.
- [ ] `sim-rng`: seeding and warmup draws, against the host's sequence for the same seed.
- [ ] `sim-data`: the typed model, first loaded from `data/game` (Python decodes for now).
- [ ] The damage pipeline, against `optimiser/hit.py`.

### 3. A first fight

- [ ] Turn loop, turn meters, the AI's choices, basic buffs and debuffs.
- [ ] The captured Ice Golem Hard 10 fight replays exactly: the same turns, every result-screen
  row.

### 4. Coverage

- [ ] Effect kinds in order of how often the corpus uses them, not champion by champion.
- [ ] Dungeons, then Clan Boss, then the Chimera (trials, the unkillable boss, the clan's HP)
  and Hydra (heads).
- [ ] `Unsupported` for everything not done, listed in the coverage report.

### 5. Setups and slices

- [ ] `sim-setup`, against the host's `build` for every corpus team.
- [ ] Slices in `sim-data`; every corpus fight run from its slice alone.

### 6. The reader as a local server

- [ ] A native Windows build (`x86_64-pc-windows-msvc`) in CI.
- [ ] Static-data decoding in Rust (MessagePack-CSharp Lz4BlockArray), against
  `tools/static_decode.py`'s output.
- [ ] Serve mode: the endpoints above, pairing, `Host`/`Origin` checks, SSE.
- [ ] The URL protocol and the export-file fallback.

### 7. The sim service

- [ ] `sim-api`: requests, version checks, limits, summaries, the result cache.
- [ ] Accounts, tokens, payments.
- [ ] Hosting: native Rust, no Wine.

### 8. The static site

- [ ] The Vue front end built as a static site, talking to the reader for data and to the API
  for sims; the FastAPI server's page props become browser-side computations.
- [ ] Free pages first (they need only the reader), then the paid Sim page.
- [ ] The HH parts removed (`webui/extractor.py`, `capture/`, the Equip, Preview and Sell
  buttons).

### 9. Release

- [ ] Installer, code signing, checksums.
- [ ] The game-update runbook above, rehearsed on a real update.

## Open questions

- **Plarium:** what they'd allow, and on what terms. A data-use permission is likelier than a
  code licence, and would change principle 2.
- **Price:** tokens per fight, weighted how, and how many free.
- **Browsers:** how Local Network Access prompts behave across Chrome, Edge and Firefox by
  launch, and whether Safari matters (players are on Windows).
- **The gear optimiser:** in the browser (HiGHS in WASM), or left to HH.
- **Where the Python goes:** much of `optimiser/` feeds pages the static site needs (events,
  info pages); ported to TypeScript, or to Rust compiled to WASM.
