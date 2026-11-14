//! Stage progress: `UserWrapper.Stages` → `StageWrapperReadOnly.StageData` →
//! `UserStageData.BattleResultsByStageId`, each stage's `StageStats`. Only stages the account
//! has fought are in it.
//!
//! - `Progress`: a stage's result, as the game keeps it
//! - `read`: stage id → its progress

use std::collections::BTreeMap;

use serde::Serialize;

use crate::collections::dict_refs;
use crate::layout::{offsets, Layout};
use crate::process::Process;

offsets!(StatsFields, "StageStats" { passed: "Passed", stars: "Stars" });

#[derive(Serialize)]
pub struct Progress {
    pub passed: bool,
    /// the game's `Stars`: how it counts the stage's battle quests (stars) done
    pub stars: i32,
}

pub fn read(
    process: &Process,
    layout: &Layout,
    user: u64,
) -> Result<BTreeMap<i32, Progress>, String> {
    let fields = StatsFields::new(layout)?;
    let path = ["UserWrapper.Stages", "StageWrapperReadOnly.StageData"];
    let data = layout.follow(process, user, &path)?;
    let results = process.read(data + layout.field("UserStageData.BattleResultsByStageId")?)?;

    dict_refs(process, results)?
        .into_iter()
        .map(|(stage, stats)| {
            let b = process.block(stats, fields.span)?;
            let progress = Progress { passed: b.bool(fields.passed), stars: b.i32(fields.stars) };
            Ok((stage, progress))
        })
        .collect()
}
