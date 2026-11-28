//! The server's battle settings the game runs fights with:
//! `SharedModelManager.GameParameters.BattleSettings`. Only what changes how a fight plays out
//! (turn limits, random warm-up, engine switches), under the game's field names, so the game's
//! own JSON reader takes them back (the battle host, `host/`).
//!
//! - `BattleSettings`: those fields
//! - `read`: them, if the game has its parameters loaded (warns otherwise)

use std::collections::BTreeMap;

use serde::Serialize;

use crate::collections::{dict_i32, list_i32};
use crate::layout::{offsets, Layout};
use crate::process::Process;
use crate::roots;

const MANAGER: &str = "SharedModel.SharedModelManager";

offsets!(SettingsFields, "BattleSettings" {
    engine: "ActiveEngineVersion",
    depth: "MaxEffectProcessingDepth",
    disabled: "DisabledEffects",
    max_turns: "MaxTurnsInBattle",
    max_turns_by_area: "SpecificMaxTurnsInBattleByArea",
    passive_target: "DeterminePassiveTargetJustFromEffect",
    destroy_unapply: "DestroyUnapplyEffectWhenSkipMultipleReapplying",
    late_queue: "CanProcessSkillsInLateQueue",
    double_bosses: "SimplifiedPathFindingOnDoubleBossesEnabled",
    newbie_defence: "NewbieDefenceRebalanceEnabled",
    warmup: "WarmupBattleRandomCount",
    phases: "PlayableEffectPhasesEnabled",
    pools_disabled: "BattlePoolsDisabled",
    buffer_capacity: "BattleReusableBufferInitCapacity",
    goblin_turns: "GoldenGoblinTurnLimit",
    world_boss_turns: "WorldBossTurnLimit",
    unlimited_damage: "UnlimitedDamageTakenBaseHeroTypeIds",
});

#[derive(Serialize)]
#[serde(rename_all = "PascalCase")]
pub struct BattleSettings {
    pub active_engine_version: i32,
    pub max_effect_processing_depth: i32,
    /// `EffectKindId` values
    pub disabled_effects: Vec<i32>,
    pub max_turns_in_battle: i32,
    /// `AreaTypeId` value -> turns
    pub specific_max_turns_in_battle_by_area: BTreeMap<i32, i32>,
    pub determine_passive_target_just_from_effect: bool,
    pub destroy_unapply_effect_when_skip_multiple_reapplying: bool,
    pub can_process_skills_in_late_queue: bool,
    pub simplified_path_finding_on_double_bosses_enabled: bool,
    pub newbie_defence_rebalance_enabled: bool,
    pub warmup_battle_random_count: i32,
    pub playable_effect_phases_enabled: bool,
    pub battle_pools_disabled: bool,
    pub battle_reusable_buffer_init_capacity: Option<i32>,
    pub golden_goblin_turn_limit: i32,
    pub world_boss_turn_limit: i32,
    pub unlimited_damage_taken_base_hero_type_ids: Vec<i32>,
}

pub fn read(process: &Process, layout: &Layout) -> Result<Option<BattleSettings>, String> {
    match settings(process, layout) {
        Ok(settings) => Ok(Some(settings)),
        Err(e) => {
            eprintln!("no battle settings: {e}");
            Ok(None)
        }
    }
}

fn settings(process: &Process, layout: &Layout) -> Result<BattleSettings, String> {
    let fields = SettingsFields::new(layout)?;
    let statics = roots::statics(process, layout, MANAGER)?;
    let parameters = process.ptr(
        statics + layout.field("SharedModelManager.GameParameters")?,
        "GameParameters",
    )?;
    let settings = process.ptr(
        parameters + layout.field("GameParameters.BattleSettings")?,
        "BattleSettings",
    )?;
    let b = process.block(settings, fields.span)?;
    let ints = |list: u64| if list == 0 { Ok(vec![]) } else { list_i32(process, list) };
    let by_area = |dict: u64| -> Result<BTreeMap<i32, i32>, String> {
        Ok(if dict == 0 { vec![] } else { dict_i32(process, dict)? }.into_iter().collect())
    };

    Ok(BattleSettings {
        active_engine_version: b.i32(fields.engine),
        max_effect_processing_depth: b.i32(fields.depth),
        disabled_effects: ints(b.ptr(fields.disabled))?,
        max_turns_in_battle: b.i32(fields.max_turns),
        specific_max_turns_in_battle_by_area: by_area(b.ptr(fields.max_turns_by_area))?,
        determine_passive_target_just_from_effect: b.bool(fields.passive_target),
        destroy_unapply_effect_when_skip_multiple_reapplying: b.bool(fields.destroy_unapply),
        can_process_skills_in_late_queue: b.bool(fields.late_queue),
        simplified_path_finding_on_double_bosses_enabled: b.bool(fields.double_bosses),
        newbie_defence_rebalance_enabled: b.bool(fields.newbie_defence),
        warmup_battle_random_count: b.i32(fields.warmup),
        playable_effect_phases_enabled: b.bool(fields.phases),
        battle_pools_disabled: b.bool(fields.pools_disabled),
        battle_reusable_buffer_init_capacity: b.nullable_i32(fields.buffer_capacity),
        golden_goblin_turn_limit: b.i32(fields.goblin_turns),
        world_boss_turn_limit: b.i32(fields.world_boss_turns),
        unlimited_damage_taken_base_hero_type_ids: ints(b.ptr(fields.unlimited_damage))?,
    })
}
