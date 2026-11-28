//! Finished fights, as the game keeps them: every live `BattleResult` in its memory (the last
//! fight's, kept for its result screen; a background run's, kept by the runs service). Nothing
//! holds them on a path from the app model, so they're found by searching the heap for objects
//! of that class (their header points at it), read only like everything here. Each is written in
//! the shape of the battle host's results (the game's JSON keys: `optimiser.fights` reads
//! either), with its setup's id, so a captured fight's replay can be checked against the real one.
//!
//! - `read`: every finished fight found, by its setup's id
//! - `fight`, `setup`, `heroes`, `rounds`, `row`, `trials`: one fight's parts
//! - `guid`: a .NET `Guid` as text

use std::collections::BTreeMap;

use serde_json::{json, Map, Value};

use crate::collections::{dict_refs, list_refs};
use crate::il2cpp::{object_class, Class};
use crate::layout::{offsets, Layout};
use crate::process::Process;

const RESULT: &str = "SharedModel.Battle.Core.Result.BattleResult";
const SETUP: &str = "SharedModel.Battle.Core.Setup.BattleSetup";
const CHALLENGE: &str = "SharedModel.Battle.Core.Hero.Challenge";

offsets!(ResultFields, "BattleResult" {
    outcome: "ResultType", finish: "FinishCause", setup: "Setup", state: "FinalState",
    statistics: "Statistics",
});
offsets!(SetupFields, "BattleSetup" { id: "Id", seed: "RandomSeed", stage: "StageId", start: "StartTime" });
offsets!(StateFields, "BattleState" {
    turn: "CurrentTurn", team_turns: "PlayerTurnCount", finished: "BattleFinished",
    enemies: "SecondTeam",
});
offsets!(ChallengeFields, "Challenge" {
    started: "IsStarted", target: "TargetProgress", progress: "CurrentProgress",
    completed: "SelfTurnWhichCompleted",
});
offsets!(HeroFields, "HeroStatistics" {
    owner: "TeamOwnerId", id: "Id", type_id: "TypeId", rounds: "_statsPerRound",
});
offsets!(RoundFields, "HeroBattleStatistics" { turns: "_statisticsByTurn", count: "TurnsCount" });
offsets!(RowFields, "TurnStatistics" {
    producer: "ProducerId", target: "TargetId", dealt: "DamageDealt", restored: "RestoredHp",
});

/// Setup id → the fight, in the host's result shape.
pub fn read(process: &Process, layout: &Layout) -> Result<BTreeMap<String, Value>, String> {
    let class = Class::from_type_info(process, layout.type_info(RESULT)?, RESULT)?;
    let mut fights = BTreeMap::new();

    for candidate in process.find_words(class.addr) {
        if let Ok(Some((id, fight))) = fight(process, layout, candidate) {
            fights.insert(id, fight);
        }
    }

    Ok(fights)
}

/// One result, if the object there really is one (a finished fight with its setup): the heap
/// also holds stale copies and values that only look like the class pointer.
fn fight(process: &Process, layout: &Layout, addr: u64) -> Result<Option<(String, Value)>, String> {
    let fields = ResultFields::new(layout)?;
    let b = process.block(addr, fields.span)?;
    let outcome = b.i32(fields.outcome);
    let (setup_addr, state_addr, statistics) = (b.ptr(fields.setup), b.ptr(fields.state), b.ptr(fields.statistics));

    if !(1..=3).contains(&outcome) || setup_addr == 0 || state_addr == 0 || statistics == 0 {
        return Ok(None);
    }

    if object_class(process, setup_addr)?.full_name(process)? != SETUP {
        return Ok(None);
    }

    let (id, setup) = setup(process, layout, setup_addr)?;
    let state_fields = StateFields::new(layout)?;
    let state = process.block(state_addr, state_fields.span)?;
    let by_hero = process.read(statistics + layout.field("BattleStatistics.StatisticsByHero")?)?;

    Ok(Some((
        id,
        json!({
            "i": outcome,
            "c": b.i32(fields.finish),
            "p": setup,
            "s": {
                "t": state.i32(state_fields.turn),
                "pt": state.i32(state_fields.team_turns),
                "b": state.bool(state_fields.finished),
                "s": {"h": trials(process, layout, state.ptr(state_fields.enemies))?},
            },
            "x": {"d": heroes(process, layout, by_hero)?},
        }),
    )))
}

fn setup(process: &Process, layout: &Layout, addr: u64) -> Result<(String, Value), String> {
    let fields = SetupFields::new(layout)?;
    let b = process.block(addr, fields.span)?;
    let id = guid(&process.block(addr + fields.id, 16)?.bytes(0, 16));

    Ok((
        id.clone(),
        json!({"z": id, "r": b.i32(fields.seed), "i": b.i32(fields.stage), "t": b.unix_seconds(fields.start)}),
    ))
}

fn heroes(process: &Process, layout: &Layout, by_hero: u64) -> Result<Value, String> {
    let fields = HeroFields::new(layout)?;
    let mut heroes = Map::new();

    for (battle_id, addr) in dict_refs(process, by_hero)? {
        let b = process.block(addr, fields.span)?;
        heroes.insert(
            battle_id.to_string(),
            json!({
                "o": b.i64(fields.owner),
                "i": b.i32(fields.id),
                "t": b.i32(fields.type_id),
                "r": rounds(process, layout, b.ptr(fields.rounds))?,
            }),
        );
    }

    Ok(Value::Object(heroes))
}

fn rounds(process: &Process, layout: &Layout, by_round: u64) -> Result<Value, String> {
    let fields = RoundFields::new(layout)?;
    let mut rounds = Map::new();

    if by_round == 0 {
        return Ok(Value::Object(rounds));
    }

    for (round, addr) in dict_refs(process, by_round)? {
        let b = process.block(addr, fields.span)?;
        let mut turns = Map::new();

        for (turn, list) in dict_refs(process, b.ptr(fields.turns))? {
            let rows = list_refs(process, list)?
                .into_iter()
                .filter(|&r| r != 0)
                .map(|r| row(process, layout, r))
                .collect::<Result<Vec<_>, String>>()?;
            turns.insert(turn.to_string(), Value::Array(rows));
        }

        rounds.insert(round.to_string(), json!({"r": turns, "t": b.i32(fields.count)}));
    }

    Ok(Value::Object(rounds))
}

/// A `TurnStatistics` row as the game's JSON names it: producer `z`, target `x`, damage dealt
/// `d`, HP restored `h`.
fn row(process: &Process, layout: &Layout, addr: u64) -> Result<Value, String> {
    let fields = RowFields::new(layout)?;
    let b = process.block(addr, fields.span)?;

    Ok(json!({
        "z": b.i32(fields.producer),
        "x": b.i32(fields.target),
        "d": b.nullable_i32(fields.dealt),
        "h": b.nullable_i32(fields.restored),
    }))
}

/// The enemy team's heroes with their trials (`BattleHero.Challenges`: the Chimera's), each as
/// the game's JSON has it: started `s`, target `mp` and progress `cp` (raw `Fixed`), the boss's
/// turn it was completed on `t`. Other enemies come out with none. An entry whose object is no
/// longer a `Challenge` (the game reuses some after the fight) is left out.
fn trials(process: &Process, layout: &Layout, team: u64) -> Result<Value, String> {
    let fields = ChallengeFields::new(layout)?;
    let mut heroes = Vec::new();

    if team == 0 {
        return Ok(Value::Array(heroes));
    }

    for hero in list_refs(process, process.read(team + layout.field("BattleTeam.Heroes")?)?)? {
        let by_skill = process.read(hero + layout.field("BattleHero.Challenges")?)?;
        let mut challenges = Map::new();

        for (skill, addr) in if by_skill == 0 { Vec::new() } else { dict_refs(process, by_skill)? } {
            if addr == 0 || object_class(process, addr)?.full_name(process)? != CHALLENGE {
                continue;
            }

            let b = process.block(addr, fields.span)?;
            challenges.insert(
                skill.to_string(),
                json!({
                    "s": b.bool(fields.started),
                    "mp": b.i64(fields.target),
                    "cp": b.i64(fields.progress),
                    "t": b.nullable_i32(fields.completed),
                }),
            );
        }

        heroes.push(json!({"ch": challenges}));
    }

    Ok(Value::Array(heroes))
}

/// A `System.Guid`'s 16 bytes (an int, two shorts, eight bytes) as its text.
fn guid(bytes: &[u8]) -> String {
    let int = u32::from_le_bytes(bytes[0..4].try_into().unwrap());
    let short1 = u16::from_le_bytes(bytes[4..6].try_into().unwrap());
    let short2 = u16::from_le_bytes(bytes[6..8].try_into().unwrap());
    let tail: String = bytes[8..16].iter().map(|b| format!("{b:02x}")).collect();
    format!("{int:08x}-{short1:04x}-{short2:04x}-{}-{}", &tail[..4], &tail[4..])
}
