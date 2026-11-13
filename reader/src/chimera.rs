//! The Chimera's current raid: `SharedModelManager.DynamicData.StageData.AllianceChimeraData`.
//! Which trials give which rewards follows from its prize offset (`optimiser.chimera.rotation`).
//!
//! - `Raid`: when the raid started, its number and its prize offset
//! - `read`: the raid, if the game has one loaded (warns otherwise)

use serde::Serialize;

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

#[derive(Serialize)]
pub struct Raid {
    /// Unix seconds
    pub start: i64,
    pub number: i32,
    pub prize_offset: i32,
}

pub fn read(process: &Process, layout: &Layout) -> Result<Option<Raid>, String> {
    match raid(process, layout) {
        Ok(raid) => Ok(Some(raid)),
        Err(e) => {
            eprintln!("no Chimera raid: {e}");
            Ok(None)
        }
    }
}

fn raid(process: &Process, layout: &Layout) -> Result<Raid, String> {
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
    })
}
