//! One fight on auto, as the game plays it: its `BattleProcessor` over a `BattleSetup`, each
//! turn the game's own AI's choice (`EnemyTurnActionGenerator`, which picks for whichever side
//! is acting, by the saved skill settings in the setup), applied as the commands the game
//! records. The result is the game's `BattleResult`: setup, commands, final state, statistics.
//!
//! - `run`: a setup's fight with a seed, its result as the game's JSON
//! - `Turn`, `next_turn`, `command_json`: one turn's command

use crate::game::{read_json, write_json};
use crate::il2cpp::{Il2cpp, Ptr};

/// More commands than any fight takes (a co-op run stops at 75 boss turns): a fight that gets
/// here is looping.
const MAX_COMMANDS: usize = 20_000;

/// `seed` None keeps the setup's own (a captured fight's: the fight replays exactly).
pub fn run(il2cpp: &Il2cpp, setup_json: &str, seed: Option<i32>) -> Result<String, String> {
    let setup_class = il2cpp.class("SharedModel.Battle.Core.Setup", "BattleSetup")?;
    let setup = read_json(il2cpp, setup_json, setup_class)?;

    if let Some(seed) = seed {
        il2cpp.set_i32(setup, "RandomSeed", seed)?;
    }

    let processor_class = il2cpp.class("SharedModel.Battle.Core", "BattleProcessor")?;
    let journal = il2cpp.new_object(il2cpp.class("SharedModel.Battle.Journal", "EmptyBattleJournal")?, &mut [])?;
    let (mut auto, mut player_first) = (1u8, 1u8);
    let processor = il2cpp.new_object(
        processor_class,
        &mut [setup, &mut auto as *mut u8 as Ptr, journal, &mut player_first as *mut u8 as Ptr],
    )?;

    il2cpp.call(il2cpp.method(processor_class, "StartBattle", 0)?, processor, &mut [])?;
    let context = il2cpp.call(il2cpp.method(processor_class, "get_Context", 0)?, processor, &mut [])?;
    let generator_class = il2cpp.class("SharedModel.Battle.AI.TurnActionGeneration", "EnemyTurnActionGenerator")?;
    let generator = il2cpp.new_object(generator_class, &mut [context])?;
    let generate = il2cpp.method(generator_class, "GenerateNext", 2)?;
    let command_class = il2cpp.class("SharedModel.Battle.Core.Commands", "BattleCommand")?;
    let state_of = il2cpp.method(processor_class, "get_State", 0)?;
    let apply = il2cpp.method(processor_class, "ApplyCommand", 1)?;

    for _ in 0..MAX_COMMANDS {
        let state = il2cpp.call(state_of, processor, &mut [])?;

        if il2cpp.get::<u8>(state, "BattleFinished")? != 0 {
            let result = il2cpp.call(il2cpp.method(processor_class, "GetBattleResult", 0)?, processor, &mut [])?;
            return write_json(il2cpp, result);
        }

        let turn = next_turn(il2cpp, generate, generator, context)?;
        let command = read_json(il2cpp, &command_json(&turn), command_class)?;
        il2cpp.call(apply, processor, &mut [command])?;
    }

    Err(format!("the fight didn't finish in {MAX_COMMANDS} commands"))
}

/// What the AI does with the acting champion: a skill, by whom, at whom (owners are user ids,
/// -1 for the enemy's side).
pub struct Turn {
    pub skill: i32,
    pub producer: (i64, i32),
    pub target: (i64, i32),
}

fn next_turn(il2cpp: &Il2cpp, generate: Ptr, generator: Ptr, context: Ptr) -> Result<Turn, String> {
    let mut no_focus = [0u8; 8]; // Nullable<int>: none
    let action = il2cpp.call(generate, generator, &mut [context, no_focus.as_mut_ptr() as Ptr])?;

    let skill: Ptr = il2cpp.get(action, "Skill")?;
    let producer: Ptr = il2cpp.get(action, "Producer")?;
    let target = match il2cpp.get::<Ptr>(action, "Target")? {
        t if t.is_null() => producer,
        t => t,
    };
    let hero = |h: Ptr| -> Result<(i64, i32), String> {
        Ok((il2cpp.getter(h, "get_OwnerUserId")?, il2cpp.getter(h, "get_Id")?))
    };

    Ok(Turn {
        skill: il2cpp.get(skill, "TypeId")?,
        producer: hero(producer)?,
        target: hero(target)?,
    })
}

/// The `BattleCommand` the game records for a skill used (its JSON: `c` sets the cooldown).
pub fn command_json(turn: &Turn) -> String {
    let (owner, producer) = turn.producer;
    let (target_owner, target) = turn.target;
    format!(
        r#"{{"t":0,"u":{owner},"s":{{"s":{},"p":{{"p":{owner},"h":{producer}}},"t":{{"p":{target_owner},"h":{target}}},"c":1}}}}"#,
        turn.skill
    )
}
