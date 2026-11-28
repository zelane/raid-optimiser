//! Saved teams: the presets (`UserHeroData.HeroesAiPresets`) and the arena defenses.
//!
//! - `Preset`: a saved team, its area (`HeroesAiPresetType`), its champions and their skill
//!   settings (each slot's `SkillPrioritiesSetup`, as the 3v3 defenders')
//! - `presets`: every preset; an area from the id, as `HeroesAiPreset.get_Type` finds it
//! - `arena_defense`: the classic arena's defense team (`UserArenaData.DefenseHeroIds`)
//! - `arena3x3_defense`: the 3v3 arena's teams (a `TeamSetup` each)
//! - `SkillPriorities`, `arena3x3_priorities`: each 3v3 defender's skill settings (its slot's
//!   `PrioritiesSetup`): the skill it opens with, each skill's priority, and its `Sequence`s

use std::collections::BTreeMap;

use serde::Serialize;

use crate::collections::{array_i32, dict_i32, list_i32, list_refs, string};
use crate::layout::{offsets, Layout};
use crate::process::Process;
use crate::roots;

const PRESET: &str = "SharedModel.Meta.Heroes.HeroesAiPreset";
const PRESETS: [&str; 3] = [
    "UserWrapper.Heroes",
    "HeroesWrapperReadOnly.HeroData",
    "UserHeroData.HeroesAiPresets",
];
const ARENA: [&str; 2] = ["UserWrapper.Arena", "ArenaWrapperReadOnly.ArenaData"];
const ARENA3X3: [&str; 3] = [
    "UserWrapper.Arena3x3",
    "Arena3x3WrapperReadOnly.Data",
    "UserArena3X3Data.Arena3X3DefenseTeamSetup",
];
/// Ids `get_Type` answers Pvp for before consulting `TypeRanges` (the arena defenses' own)
const PVP_IDS: [i32; 5] = [0, 301, 601, 602, 603];
const PVP: i32 = 2;

offsets!(PresetFields, "HeroesAiPreset" { id: "Id", name: "Name", setups: "SkillPrioritiesSetups" });
offsets!(PrioritiesFields, "SkillPrioritiesSetup" {
    hero_id: "HeroId",
    starter: "StarterSkillId",
    priorities: "PriorityBySkillId",
    sequences: "Sequences",
});
offsets!(SequenceFields, "HeroAiPresetSequence" {
    starter: "StarterSkillId",
    starters: "StarterSkillIds",
    priorities: "PriorityBySkillId",
});

#[derive(Serialize)]
pub struct Preset {
    pub id: i32,
    pub name: String,
    pub area: String,
    pub heroes: Vec<i32>,
    pub priorities: Vec<SkillPriorities>,
}

/// A champion's skill settings: skill id → `SkillPriorityType` by name (Default, First…,
/// NotUsed), the skill it opens with, and the sequences the game keeps beside them.
#[derive(Serialize)]
pub struct SkillPriorities {
    pub hero_id: i32,
    pub starter: Option<i32>,
    pub priorities: BTreeMap<i32, String>,
    pub sequences: Vec<Sequence>,
}

#[derive(Serialize)]
pub struct Sequence {
    pub starter: Option<i32>,
    pub starters: Vec<i32>,
    pub priorities: BTreeMap<i32, String>,
}

pub fn presets(process: &Process, layout: &Layout, user: u64) -> Result<Vec<Preset>, String> {
    let fields = PresetFields::new(layout)?;
    let setup_fields = PrioritiesFields::new(layout)?;
    let sequence = SequenceFields::new(layout)?;
    let ranges = type_ranges(process, layout)?;
    let list = layout.follow(process, user, &PRESETS)?;

    list_refs(process, list)?
        .into_iter()
        .filter(|&addr| addr != 0)
        .map(|addr| {
            let b = process.block(addr, fields.span)?;
            let id = b.i32(fields.id);
            let priorities: Vec<SkillPriorities> = list_refs(process, b.ptr(fields.setups))?
                .into_iter()
                .filter(|&setup| setup != 0) // an empty slot
                .map(|setup| skill_priorities(process, layout, &setup_fields, &sequence, setup))
                .collect::<Result<_, _>>()?;

            Ok(Preset {
                id,
                name: string(process, b.ptr(fields.name))?,
                area: layout.name("HeroesAiPresetType", area_of(id, &ranges)?)?,
                heroes: priorities.iter().map(|p| p.hero_id).collect(),
                priorities,
            })
        })
        .collect()
}

pub fn arena_defense(process: &Process, layout: &Layout, user: u64) -> Result<Vec<i32>, String> {
    let data = layout.follow(process, user, &ARENA)?;
    let ids = process.read(data + layout.field("UserArenaData.DefenseHeroIds")?)?;
    array_i32(process, ids, 1)
}

pub fn arena3x3_defense(
    process: &Process,
    layout: &Layout,
    user: u64,
) -> Result<Vec<Vec<i32>>, String> {
    let hero_id = layout.field("HeroSlotSetup.InventoryHeroId")?;

    arena3x3_slots(process, layout, user)?
        .into_iter()
        .map(|team| {
            team.into_iter()
                .map(|slot| process.read(slot + hero_id))
                .collect()
        })
        .collect()
}

/// Per team, per slot: its champion's skill settings (None where the slot has none).
pub fn arena3x3_priorities(
    process: &Process,
    layout: &Layout,
    user: u64,
) -> Result<Vec<Vec<Option<SkillPriorities>>>, String> {
    let setup = layout.field("HeroSlotSetup.PrioritiesSetup")?;
    let fields = PrioritiesFields::new(layout)?;
    let sequence = SequenceFields::new(layout)?;

    arena3x3_slots(process, layout, user)?
        .into_iter()
        .map(|team| {
            team.into_iter()
                .map(|slot| match process.read::<u64>(slot + setup)? {
                    0 => Ok(None),
                    addr => skill_priorities(process, layout, &fields, &sequence, addr).map(Some),
                })
                .collect()
        })
        .collect()
}

/// The 3v3 defense's `HeroSlotSetup`s, per team, empty slots left out.
fn arena3x3_slots(process: &Process, layout: &Layout, user: u64) -> Result<Vec<Vec<u64>>, String> {
    let slots = layout.field("TeamSetup.HeroSlotSetups")?;
    let setups = layout.follow(process, user, &ARENA3X3)?;

    list_refs(process, setups)?
        .into_iter()
        .map(|team| {
            Ok(list_refs(process, process.read(team + slots)?)?
                .into_iter()
                .filter(|&slot| slot != 0)
                .collect())
        })
        .collect()
}

fn skill_priorities(
    process: &Process,
    layout: &Layout,
    fields: &PrioritiesFields,
    sequence: &SequenceFields,
    addr: u64,
) -> Result<SkillPriorities, String> {
    let b = process.block(addr, fields.span)?;
    let sequences = list_refs(process, b.ptr(fields.sequences))?
        .into_iter()
        .filter(|&s| s != 0)
        .map(|s| {
            let sb = process.block(s, sequence.span)?;
            Ok(Sequence {
                starter: sb.nullable_i32(sequence.starter),
                starters: list_i32(process, sb.ptr(sequence.starters))?,
                priorities: priority_names(process, layout, sb.ptr(sequence.priorities))?,
            })
        })
        .collect::<Result<_, String>>()?;

    Ok(SkillPriorities {
        hero_id: b.i32(fields.hero_id),
        starter: b.nullable_i32(fields.starter),
        priorities: priority_names(process, layout, b.ptr(fields.priorities))?,
        sequences,
    })
}

/// A `Dictionary<int, SkillPriorityType>`, its values by name.
fn priority_names(
    process: &Process,
    layout: &Layout,
    dict: u64,
) -> Result<BTreeMap<i32, String>, String> {
    dict_i32(process, dict)?
        .into_iter()
        .map(|(skill, priority)| Ok((skill, layout.name("SkillPriorityType", priority)?)))
        .collect()
}

/// `HeroesAiPreset.TypeRanges`: (lowest id, area) pairs, highest first.
fn type_ranges(process: &Process, layout: &Layout) -> Result<Vec<(i32, i32)>, String> {
    let statics = roots::statics(process, layout, PRESET)?;
    let array = process.read(statics + layout.field("HeroesAiPreset.TypeRanges")?)?;
    let flat = array_i32(process, array, 2)?;
    Ok(flat
        .chunks_exact(2)
        .map(|pair| (pair[0], pair[1]))
        .collect())
}

/// The first range the id reaches, as `get_Type` takes it.
fn area_of(id: i32, ranges: &[(i32, i32)]) -> Result<i32, String> {
    if PVP_IDS.contains(&id) {
        return Ok(PVP);
    }

    ranges
        .iter()
        .find(|(lowest, _)| id >= *lowest)
        .map(|(_, area)| *area)
        .ok_or_else(|| format!("preset {id} is below every TypeRanges entry"))
}
