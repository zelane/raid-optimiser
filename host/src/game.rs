//! The game, set up as far as its battles need: the startup steps they depend on, its static
//! data (skills, effects, stages) loaded by its own cache loader, and the server's battle
//! settings.
//!
//! - `start`: the shared model's logging and the MessagePack formatters, as the game starts them
//! - `load_static_data`: the static data, from the cache under the host's LocalLow copy
//! - `set_battle_settings`: the server's `BattleSettings` (the reader's copy), in place
//! - `read_json`, `write_json`: objects to and from the game's own JSON

use std::ptr::null_mut;
use std::time::Instant;

use crate::il2cpp::{Il2cpp, Ptr};

/// The game's startup steps the battle model and the static data's loader need.
const STARTUP: [(&str, &str, &str); 2] = [
    ("Client.Model.Common", "SharedModelLogger", "Configure"),
    ("Client.RaidApp", "MessagePack", "Init"),
];

pub fn start(il2cpp: &Il2cpp) -> Result<(), String> {
    for (namespace, class, method) in STARTUP {
        let target = il2cpp.class(namespace, class)?;
        il2cpp
            .call(il2cpp.method(target, method, 0)?, null_mut(), &mut [])
            .map_err(|e| format!("{class}.{method}: {e}"))?;
    }

    Ok(())
}

/// Loads the static data with the game's `MessagePackStaticDataCache` and hands it to
/// `SharedModelManager.SetStaticData`, where battles read it.
pub fn load_static_data(il2cpp: &Il2cpp) -> Result<(), String> {
    let started = Instant::now();
    let cache = il2cpp.class("Client.Model.Gameplay.StaticData", "MessagePackStaticDataCache")?;
    let loader = il2cpp.new_object(cache, &mut [])?;
    let data = il2cpp.call(il2cpp.method(cache, "Load", 0)?, loader, &mut [])?;

    if data.is_null() {
        return Err("no static data in the cache (launch the game once?)".into());
    }

    let manager = il2cpp.class("SharedModel", "SharedModelManager")?;
    il2cpp.call(il2cpp.method(manager, "SetStaticData", 1)?, null_mut(), &mut [data])?;
    eprintln!("static data loaded in {:.1?}", started.elapsed());
    Ok(())
}

/// A `GameParameters` holding the server's battle settings, as `SharedModelManager`'s: the
/// battle reads its turn limits, random warm-up and engine switches there.
pub fn set_battle_settings(il2cpp: &Il2cpp, settings_json: &str) -> Result<(), String> {
    let settings_class = il2cpp.class("SharedModel.Meta.Battle", "BattleSettings")?;
    let settings = read_json(il2cpp, settings_json, settings_class)?;
    let parameters = il2cpp.new_object(il2cpp.class("SharedModel.Meta.Users", "GameParameters")?, &mut [])?;
    il2cpp.set_ref(parameters, "BattleSettings", settings)?;

    let manager = il2cpp.class("SharedModel", "SharedModelManager")?;
    il2cpp.set_static(manager, "GameParameters", parameters)
}

/// An object of `class` from the game's JSON (`JsonMain.FromJson`).
pub fn read_json(il2cpp: &Il2cpp, json: &str, class: Ptr) -> Result<Ptr, String> {
    let buffer_class = il2cpp.class("Plarium.Common.Buffers", "TextBuffer")?;
    let buffer = il2cpp.new_object(buffer_class, &mut [il2cpp.string(json)])?;
    let json_main = il2cpp.class("Plarium.Common.Serialization", "JsonMain")?;
    let mut position = 0i32;

    il2cpp.call(
        il2cpp.method(json_main, "FromJson", 3)?,
        null_mut(),
        &mut [buffer, il2cpp.type_of(class), &mut position as *mut i32 as Ptr],
    )
}

/// An object as the game's JSON (`JsonMain.ToJsonStr`, the short names its classes give).
pub fn write_json(il2cpp: &Il2cpp, object: Ptr) -> Result<String, String> {
    let json_main = il2cpp.class("Plarium.Common.Serialization", "JsonMain")?;
    let mut ignore_names = 0u8;
    let text = il2cpp.call(
        il2cpp.method(json_main, "ToJsonStr", 2)?,
        null_mut(),
        &mut [object, &mut ignore_names as *mut u8 as Ptr],
    )?;

    Ok(il2cpp.text(text))
}
