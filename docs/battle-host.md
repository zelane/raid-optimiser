# Raid battle sim: running the game's own engine

2026-11-28

## Summary

We can now sim any of the account's champions, in the gear they wear, against any stage, on the
game's own battle engine. A captured real fight replays to the exact number: 197,696,419
damage, every result-screen row the same.

- **Engine:** the game's `GameAssembly.dll`, hosted in our own process under Wine. No game
  client, no account, no network, nothing injected.
- **Teams:** each champion's slot is built by the game's own setup builders (gear, sets,
  Blessing, Academy, Great Hall, relics) from the reader's snapshot.
- **Enemies:** any stage's waves and modifiers come from static data, or from a captured fight.
- **Speed:** about 4 s a fight; 20 seeds take about 1.5 minutes.
- **First answers:** the co-op Polara team averages 172.7M a run; swapping in the second Lady
  Mikage is about even (169.5M). The Ice Golem team clears Hard 10 in 20 of 20 sims, in about
  32 turns.

## How we got here

A hand-written sim came first and landed about 10 % short of real runs; running the game's own
engine replaced it and matches real fights exactly.

1. **Hand-written sim** (`optimiser/demonlord/`, now removed): the Tainted Demon Lord and five
   champions' kits written from the static data's skill effects, with hits through `hit.py`.
   Auto's choices and several rules were approximations.
    1. Against two real runs (168M, 183M) it gave 160M, after one real fix: the boss's damage
       cap applies before the other multipliers.
    2. It undercounted Polara by about 25M, and every new team needed its kits written by hand.
2. **Hosting the game's code:** `GameAssembly.dll` starts under plain Wine outside Unity. It
   needs three Unity calls answered and two of the game's startup steps; the game's own loader
   then reads its static data.
3. **A real fight's setup:** while a fight runs, the game keeps its `BattleSetup` in the Wine
   registry (PlayerPrefs). `just capture` copies it, read-only.
4. **Replaying it:** with the server's battle settings (read from memory) and the game's AI
   choosing each turn, the captured co-op fight reproduced the user's result screen exactly.
5. **Building setups:** slots built from the account with the game's own builders reproduced the
   same fight exactly; enemy sides built from stage data matched a captured Ice Golem setup.

## How it works

Two steps run the game's own code (the host's `build` and `fight`); everything else only feeds
it and reads its results. From the account to a report:

1. **Reader snapshot** (`just read`, from the game's memory, read-only): champions, gear,
   relics, Academy, battle settings.
2. **`setups.py request`:** the account as the game's own JSON.
3. **Host: build** (game code): the game's builders make each slot's parts, with the static
   data (a copy of the cache).
4. **`setups.py assemble`:** the slots, plus the enemies from the stage's static data or from a
   captured fight (`just capture`).
5. **Host: fight, per seed** (game code): `BattleProcessor`, the game's AI picking every turn.
6. **`fights.py` report:** clears, turns, damage per champion.

The host (`host/`, Rust for Windows) loads `GameAssembly.dll` under plain Wine, in a prefix of
its own:

- **`il2cpp`:** starts the runtime and calls the game's code; managed exceptions come back with
  their whole chain.
- **`unity`:** answers the three Unity calls the code makes outside a battle (data folder,
  version, a buffer free).
- **`game`:** runs the game's startup steps (logging, MessagePack), loads its static data from a
  fresh copy of the cache, and sets the server's battle settings.
- **`build`:** the shared model's setup builders, for gear and sets, Blessing, Academy, Great
  Hall and relic stats.
- **`fight`:** `BattleProcessor` over a `BattleSetup`, each turn the AI's choice applied as the
  game's own command; writes the `BattleResult`.

The reader adds what the builders need: Blessings, relic sockets and stones, Academy guardians,
raw `Fixed` stat values and rarity glyphs, and the battle settings. `setups.py` fills in what
the server adds to a slot: relic and stone skills, skill order and levels, skill settings.

## Verification

Every check has come out exact, against the game's result screen for a co-op run and an Ice
Golem Hard 10 run.

| Check | What was compared | Result |
| --- | --- | --- |
| Captured co-op fight, replayed (team 907, seed 398343290) | Host's result vs the game's result screen | Exact: 197,696,419 total; every champion's dealt, taken and healed; 46 turns |
| Same fight, setup built from the account | Built slots vs captured slots, then the fight | Slots identical; same 197,696,419 and every row |
| Determinism | Seeds 0 to 2, run twice in separate processes | Identical per seed |
| Ice Golem Hard 10, setup built from stage data (team 1505) | Built setup vs captured setup | Both teams identical; only reward fields differ (multiplier, double run, run number) |
| Ice Golem Hard 10, same seed (2031540557) | Captured setup vs built setup, fought | Identical: Victory in 27 turns (25 the team's), 14,298,111 dealt |
| Fire Knight Hard 10, a real fight replayed (seed 1992284312), and built from stage data | Host's result vs the game's record (`just capture`); built setup vs captured | Exact: Victory, 52 turns, every row; setups identical but for reward fields |
| Ice Golem Hard 10, a real fight replayed (seed 1062678995) | Host's result vs the game's result screen | Exact: Victory, 34 turns; every champion's dealt, taken and healed |

## Results so far

Swapping the second Lady Mikage in for Polara is about even in the co-op event, and the Ice
Golem team clears Hard 10 every time in about 32 turns.

**Co-op Tainted Demon Lord, stage 5 (15019005), 20 seeds each, skill settings from saved team
910:**

| Team | Average damage a run | 9 in 10 runs between |
| --- | --- | --- |
| Venus, Lady Mikage, Polara, Arachoa, Donatello (910) | 172.7M | 162.7M and 182.3M |
| The same with the second Lady Mikage for Polara | 169.5M | 162.9M and 175.6M |
| Venus, Lady Mikage, Arachoa, Varkos, Donatello (907) | 190.9M | 179.4M and 205.6M |

The two real Polara runs (168M, 183M) and the real 907 run (197.7M) fall inside their teams'
ranges.

**Ice Golem Hard 10 (2072010), 3,000 seeds of the captured fight (6 processes, 4.5 minutes):**
cleared 2,995 of 3,000 (99.8 %, about 1 in 600 lost). The five losses (seeds 1373, 1450, 2066,
2307, 2392) all end at turns 21 to 28: the golem deals about 340k, the team's whole HP, during its
wave, while a win sees only Krixia hit (74k). Wins take 31.7 turns on average (24 to 68).

**Fire Knight Hard 10 (2082010, the data's `FireGolemCave`), 3,000 seeds of a captured fight
(Senna, Lady Mikage, Arachoa, Toshiro, Neldor; saved team 1503):** cleared 2,990 of 3,000 (99.7 %,
about 1 in 300 lost). The capture replays exactly (a win in 52 turns), and the setup built from the
account and the stage data matches the server's field for field. Losses are long, 157 to 286
turns, unlike the Ice Golem's quick wipes; wins take 57.4 turns on average but range from 31 to 425.

**Ice Golem Hard 10 (2072010), 20 seeds, Marius, Lady Mikage, Night Queen Krixia, Helicath,
Toshiro, skill settings from saved team 5:** cleared 20 of 20. A win took 31.6 turns on average
(25 to 42), 28.6 of them the team's (22 to 37). Marius and Toshiro deal about 7M each of the
14.9M.

## How to use it

Three recipes cover it: `just sim` for a team against a stage, `just capture` to save a real
fight, `just fight` to replay one.

| Command | What it does | Example |
| --- | --- | --- |
| `just sim <stage or setup file> <champion ids> [seeds] [saved team]` | Builds the champions' slots from the snapshot, puts them against the stage's enemies (or a captured fight's), and fights them on auto | `just sim 2072010 22704,16470,21539,16536,21504 20 5` |
| `just capture` | Captures the next fight whole: its setup as it starts, its result from the game's memory once it's over, then checks the replay against it | Run it, then start the fight |
| `just check-capture <setup file>` | Replays a captured fight on its own seed and compares outcome, turns and every result-screen row with the game's record | `just check-capture data/captures/setups/20261128-142636-2072010.json` |
| `just fight <setup file> [seeds] [jobs]` | Fights a setup as it is, the seeds split over several processes; seed 0 is the setup's own, so a captured fight replays exactly. Lists the seeds that weren't cleared | `just fight data/captures/setups/20261128-142636-2072010.json 3000 6` |

The report gives how often a fight was won and the turns a win took, then each champion's
damage dealt, damage taken and healing (seed 0, and the average over seeds). A boss fight that
counts boss turns, like the co-op boss, adds them.

Skill settings come from the saved team named, else from the captured fight, else auto's
defaults. A saved team keeps one set of settings per wave, and the sim uses them.

It needs a current snapshot: `just read` with the game running, or `just watch` restarted after
the reader changes.

## Findings along the way

The biggest finding for the optimiser is that its stat model has been missing the Academy and
Blessings.

- **Missing stats:** in battle Venus has 300 SPD, 2,548 ATK and 56,272 HP; our model gave 277,
  2,390 and 54,008. The Academy accounts for part of it (Venus +10 % HP/ATK). Blessings are
  large: Lady Mikage's adds 11,500 HP, 900 ATK, 750 DEF and 45 % C.DMG.
- **Exact values:** the game holds stats as `Fixed` (Q32.32). A substat summed from rolls isn't
  the rounded value's `Fixed`, so the reader now keeps the raw values too.
- **Mythical pieces:** their upgraded lines carry a rarity glyph (`RarityBasedPowerUpValue`), up
  to +22 ATK or +5 SPD a line. The reader didn't read it before.
- **Server settings that change fights:** 10 random draws before every battle
  (`WarmupBattleRandomCount`), a 75-turn cap on co-op runs, 1,500 turns on stages, and the
  co-op boss's damage taken is uncapped.
- **Turns:** the result screen's "Turns" is `BattleState.CurrentTurn`, every champion's and
  enemy's turns, not the team's alone.
- **Capturing:** the setup cache isn't always emptied between fights (auto repeats keep it), so
  `just capture` waits for a setup id (`z`) it hasn't seen.
- **Results from memory:** the game keeps the last fight's `BattleResult` (for its result screen,
  and a background run's in the runs service), on no fixed path. The reader finds it by
  searching the heap for objects of its class (about 6 s), so a captured fight is checked against
  the game's own record, with no screenshot: the Ice Golem fight's replay matched it.
- **Auto:** `GetDefaultSkill` is the A1, not auto's pick. The real choice comes from the game's
  AI (`EnemyTurnActionGenerator`), which serves both sides.
- **The co-op multiplier** (×1.5 at 1.39B global points) is shown beside event points, not in
  battle. Damage on the result screen doesn't include it.
- **An incident:** the first host run pointed the game's cache loader at the real static-data
  cache, and a failed load deleted it. A game restart restored it. The host now only ever sees
  a fresh copy.

## Open questions and next steps

Settled by the Ice Golem result screen: the game's "Turns" is the battle's turn counter
(`CurrentTurn`, 34 in that fight; the team's own were 31), and the team's damage taken really is
0 for all but Krixia. Gear and relic what-ifs are the closest next feature.

- [ ] **What-ifs:** change gear or relics before a sim ("does relic X raise damage"), as an
  option on `just sim`.
- [ ] **Chimera trials:** capture a Chimera fight, then read which trials a run clears from its
  result.
- [ ] **More bosses:** stages work from static data; check Clan Boss, Hydra and Chimera setups
  against one capture each, as for Ice Golem.
- [ ] **Optimiser stats:** add the Academy and Blessings to `stats.py`, which the optimiser's
  solves use.
