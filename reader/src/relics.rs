//! Relics: `UserWrapper.Relics.RelicsData`.
//!
//! - `Relic`: one relic
//! - `read`: every relic, and champion id → the ids of the relics they wear

use std::collections::BTreeMap;

use serde::Serialize;

use crate::collections::{dict_refs, list_i32, list_refs};
use crate::layout::{offsets, Layout};
use crate::process::Process;

const PATH: [&str; 2] = ["UserWrapper.Relics", "RelicsWrapperReadonly.RelicsData"];

offsets!(RelicFields, "Relic" { id: "Id", type_id: "TypeId", rank: "Rank", level: "Level" });
offsets!(DataFields, "UserRelicData" { relics: "Relics", by_hero: "RelicDataByHeroId" });

#[derive(Serialize)]
pub struct Relic {
    pub id: i32,
    pub type_id: i32,
    pub rank: i32,
    pub level: i32,
}

pub type Worn = BTreeMap<i32, Vec<i32>>;

pub fn read(process: &Process, layout: &Layout, user: u64) -> Result<(Vec<Relic>, Worn), String> {
    let relic = RelicFields::new(layout)?;
    let data = DataFields::new(layout)?;
    let ids = layout.field("HeroRelicData.RelicIds")?;
    let d = process.block(layout.follow(process, user, &PATH)?, data.span)?;

    let relics = list_refs(process, d.ptr(data.relics))?
        .into_iter()
        .map(|addr| {
            let b = process.block(addr, relic.span)?;
            Ok(Relic {
                id: b.i32(relic.id),
                type_id: b.i32(relic.type_id),
                rank: b.i32(relic.rank),
                level: b.i32(relic.level),
            })
        })
        .collect::<Result<_, String>>()?;
    let worn = dict_refs(process, d.ptr(data.by_hero))?
        .into_iter()
        .map(|(hero, data)| Ok((hero, list_i32(process, process.read(data + ids)?)?)))
        .collect::<Result<_, String>>()?;

    Ok((relics, worn))
}
