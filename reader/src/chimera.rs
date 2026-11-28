//! The Chimera's current raid: `SharedModelManager.DynamicData.StageData.AllianceChimeraData`.
//! Which trials give which rewards follows from its prize offset (`optimiser.chimera.rotation`).
//! And the clan's Chimeras, one per difficulty, with the HP they have left this raid
//! (`UserWrapper.Alliance` → `Alliance.GameData.ChimeraData.Chimeras`): the server starts a fight
//! there (the boss's `InitialState`, its HP less its top).
//!
//! - `Raid`: when the raid started, its number, its prize offset, the HP left by difficulty
//! - `read`: the raid, if the game has one loaded (warns otherwise)

use std::collections::BTreeMap;

use serde::Serialize;

use crate::collections::list_refs;

use crate::layout::{offsets, Layout};
use crate::process::Process;
use crate::roots;

const MANAGER: &str = "SharedModel.SharedModelManager";
const PATH: [&str; 2] = [
    "DynamicData.StageData",
    "DynamicStageData.AllianceChimeraData",
];

offsets!(RaidFields, "ChimeraData" {
    start: "RaidStartTime", number: "RaidNumber", prize_offset: "PrizeOffset",
});

offsets!(ChimeraFields, "AllianceChimera" { difficulty: "Difficulty", health_left: "HealthLeft" });

const CLAN: [&str; 4] = [
    "UserWrapper.Alliance",
    "AllianceWrapperReadonly.Alliance",
    "Alliance.GameData",
    "AllianceGameData.ChimeraData",
];

#[derive(Serialize)]
pub struct Raid {
    /// Unix seconds
    pub start: i64,
    pub number: i32,
    pub prize_offset: i32,
    /// Difficulty name → HP left (empty: no clan, or its data not loaded)
    pub health_left: BTreeMap<String, i64>,
}

pub fn read(process: &Process, layout: &Layout, user: u64) -> Result<Option<Raid>, String> {
    match raid(process, layout, user) {
        Ok(raid) => Ok(Some(raid)),
        Err(e) => {
            eprintln!("no Chimera raid: {e}");
            Ok(None)
        }
    }
}

fn raid(process: &Process, layout: &Layout, user: u64) -> Result<Raid, String> {
    let fields = RaidFields::new(layout)?;
    let statics = roots::statics(process, layout, MANAGER)?;
    let dynamic = process.ptr(
        statics + layout.field("SharedModelManager.DynamicData")?,
        "DynamicData",
    )?;
    let data = process.block(layout.follow(process, dynamic, &PATH)?, fields.span)?;

    Ok(Raid {
        start: data.unix_seconds(fields.start),
        number: data.i32(fields.number),
        prize_offset: data.i32(fields.prize_offset),
        health_left: health_left(process, layout, user).unwrap_or_else(|e| {
            eprintln!("no Chimera HP for the clan: {e}");
            BTreeMap::new()
        }),
    })
}

fn health_left(process: &Process, layout: &Layout, user: u64) -> Result<BTreeMap<String, i64>, String> {
    let fields = ChimeraFields::new(layout)?;
    let data = layout.follow(process, user, &CLAN)?;
    let chimeras = process.read(data + layout.field("AllianceChimeraData.Chimeras")?)?;
    let mut left = BTreeMap::new();

    for chimera in list_refs(process, chimeras)? {
        let b = process.block(chimera, fields.span)?;
        let difficulty = layout.name("AllianceChimeraDifficulty", b.i32(fields.difficulty))?;
        left.insert(difficulty, b.i64(fields.health_left));
    }

    Ok(left)
}
