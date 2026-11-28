//! A team's slots, the parts the game computes for each champion built by the game's own code
//! (the shared model's setup builders, which the server uses too) from the game's own objects
//! as its JSON: gear and its sets, the Blessing, the Academy, the Great Hall and the relic. The
//! rest of a slot (rank, level, skills, masteries, skill settings) is the account's as it is,
//! so `optimiser.setups` puts the slot together.
//!
//! Request: `{"guardians": UserAcademyGuardiansData, "village": UserVillageData, "champions":
//! [{"type_id", "hero": Hero, "artifacts": UserArtifactData, "relics": UserRelicData}]}`.
//! Answer: per champion `{"b", "e", "bl", "c", "z", "re"}`, the HeroSlotSetup's own keys.
//!
//! - `build`: the request answered
//! - `parts`, `hero_type`: one champion's parts, and its type from the static data

use serde_json::{json, Value};

use crate::game::{read_json, write_json};
use crate::il2cpp::{Il2cpp, Ptr};

const SETUP: &str = "SharedModel.Battle.Core.Setup";

pub fn build(il2cpp: &Il2cpp, request: &str) -> Result<String, String> {
    let request: Value = serde_json::from_str(request).map_err(|e| e.to_string())?;
    let academy = il2cpp.class("SharedModel.Meta.Academy.User", "UserAcademyGuardiansData")?;
    let village = il2cpp.class("SharedModel.Meta.Village", "UserVillageData")?;
    let guardians = read_json(il2cpp, &request["guardians"].to_string(), academy)?;
    let village = read_json(il2cpp, &request["village"].to_string(), village)?;

    let champions = request["champions"]
        .as_array()
        .ok_or("no champions in the request")?
        .iter()
        .map(|champion| parts(il2cpp, champion, guardians, village))
        .collect::<Result<Vec<_>, String>>()?;

    Ok(Value::Array(champions).to_string())
}

fn parts(il2cpp: &Il2cpp, champion: &Value, guardians: Ptr, village: Ptr) -> Result<Value, String> {
    let type_id = champion["type_id"].as_i64().ok_or("a champion without type_id")? as i32;
    let hero_type = hero_type(il2cpp, type_id)?;

    let hero_class = il2cpp.class("SharedModel.Meta.Heroes", "Hero")?;
    let hero = read_json(il2cpp, &champion["hero"].to_string(), hero_class)?;
    let artifact_data = il2cpp.class("SharedModel.Meta.Artifacts", "UserArtifactData")?;
    let artifacts: Ptr = il2cpp.get(read_json(il2cpp, &champion["artifacts"].to_string(), artifact_data)?, "Artifacts")?;
    let relic_data = il2cpp.class("SharedModel.Meta.Relics.UserData", "UserRelicData")?;
    let relics: Ptr = il2cpp.get(read_json(il2cpp, &champion["relics"].to_string(), relic_data)?, "Relics")?;

    let artifact_extensions = il2cpp.class("SharedModel.Meta.Artifacts", "ArtifactExtensions")?;
    let setups = static_call(il2cpp, artifact_extensions, "ToArtifactSetups", &mut [artifacts])?;
    let sets = static_call(il2cpp, artifact_extensions, "GetArtifactSetBonuses", &mut [setups])?;
    let blessing = static_call(il2cpp, il2cpp.class(SETUP, "BlessingSetup")?, "From", &mut [hero])?;
    let academy = static_call(il2cpp, il2cpp.class(SETUP, "AcademySetup")?, "Create", &mut [guardians, hero_type])?;
    let mut no_location = [0u8; 8]; // Nullable<ObservatoryLocationId>: none
    let building = static_call(
        il2cpp,
        il2cpp.class(SETUP, "BuildingSetup")?,
        "FromVillageData",
        &mut [village, hero_type, no_location.as_mut_ptr() as Ptr],
    )?;
    let relic_setups = static_call(il2cpp, il2cpp.class("SharedModel.Meta.Relics", "RelicExtensions")?, "ToRelicSetups", &mut [relics])?;

    Ok(json!({
        "b": as_json(il2cpp, setups)?,
        "e": as_json(il2cpp, sets)?,
        "bl": as_json(il2cpp, blessing)?,
        "c": as_json(il2cpp, academy)?,
        "z": as_json(il2cpp, building)?,
        "re": as_json(il2cpp, relic_setups)?,
    }))
}

/// `SharedModelManager.StaticData.HeroData.HeroTypeById[type_id]`.
fn hero_type(il2cpp: &Il2cpp, type_id: i32) -> Result<Ptr, String> {
    let manager = il2cpp.class("SharedModel", "SharedModelManager")?;
    let static_data = il2cpp.get_static(manager, "StaticData")?;
    let hero_data: Ptr = il2cpp.get(static_data, "HeroData")?;
    let by_id: Ptr = il2cpp.get(hero_data, "HeroTypeById")?;
    let mut key = type_id;
    let get_item = il2cpp.method(il2cpp.class_of(by_id), "get_Item", 1)?;

    il2cpp
        .call(get_item, by_id, &mut [&mut key as *mut i32 as Ptr])
        .map_err(|e| format!("no hero type {type_id}: {e}"))
}

fn static_call(il2cpp: &Il2cpp, class: Ptr, name: &str, arguments: &mut [Ptr]) -> Result<Ptr, String> {
    il2cpp
        .call(il2cpp.method(class, name, arguments.len() as i32)?, std::ptr::null_mut(), arguments)
        .map_err(|e| format!("{name}: {e}"))
}

fn as_json(il2cpp: &Il2cpp, object: Ptr) -> Result<Value, String> {
    if object.is_null() {
        return Ok(Value::Null);
    }

    serde_json::from_str(&write_json(il2cpp, object)?).map_err(|e| e.to_string())
}
