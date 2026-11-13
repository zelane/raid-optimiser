//! Saved teams: the presets (`UserHeroData.HeroesAiPresets`) and the arena defenses.
//!
//! - `Preset`: a saved team, its area (`HeroesAiPresetType`) and its champions
//! - `presets`: every preset; an area from the id, as `HeroesAiPreset.get_Type` finds it
//! - `arena_defense`: the classic arena's defense team (`UserArenaData.DefenseHeroIds`)
//! - `arena3x3_defense`: the 3v3 arena's teams (a `TeamSetup` each)

use serde::Serialize;

use crate::collections::{array_i32, list_refs, string};
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

#[derive(Serialize)]
pub struct Preset {
    pub id: i32,
    pub name: String,
    pub area: String,
    pub heroes: Vec<i32>,
}

pub fn presets(process: &Process, layout: &Layout, user: u64) -> Result<Vec<Preset>, String> {
    let fields = PresetFields::new(layout)?;
    let hero_id = layout.field("SkillPrioritiesSetup.HeroId")?;
    let ranges = type_ranges(process, layout)?;
    let list = layout.follow(process, user, &PRESETS)?;

    list_refs(process, list)?
        .into_iter()
        .filter(|&addr| addr != 0)
        .map(|addr| {
            let b = process.block(addr, fields.span)?;
            let id = b.i32(fields.id);
            let heroes = list_refs(process, b.ptr(fields.setups))?
                .into_iter()
                .filter(|&setup| setup != 0) // an empty slot
                .map(|setup| process.read(setup + hero_id))
                .collect::<Result<_, _>>()?;

            Ok(Preset {
                id,
                name: string(process, b.ptr(fields.name))?,
                area: layout.name("HeroesAiPresetType", area_of(id, &ranges)?)?,
                heroes,
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
    let slots = layout.field("TeamSetup.HeroSlotSetups")?;
    let hero_id = layout.field("HeroSlotSetup.InventoryHeroId")?;
    let setups = layout.follow(process, user, &ARENA3X3)?;

    list_refs(process, setups)?
        .into_iter()
        .map(|team| {
            list_refs(process, process.read(team + slots)?)?
                .into_iter()
                .filter(|&slot| slot != 0)
                .map(|slot| process.read(slot + hero_id))
                .collect()
        })
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
