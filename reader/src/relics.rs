//! Relics: `UserWrapper.Relics.RelicsData`.
//!
//! - `Relic`, `Socket`: one relic, and a socket for a stone in it
//! - `Stone`: one relic stone (`RelicStone`: what a socket's `stone` names)
//! - `read`: every relic, champion id → the ids of the relics they wear, and every stone

use std::collections::BTreeMap;

use serde::Serialize;

use crate::collections::{dict_refs, list_i32, list_refs};
use crate::layout::{offsets, Layout};
use crate::process::Process;

const PATH: [&str; 2] = ["UserWrapper.Relics", "RelicsWrapperReadonly.RelicsData"];

offsets!(RelicFields, "Relic" {
    id: "Id", type_id: "TypeId", rank: "Rank", level: "Level", sockets: "Sockets",
});
offsets!(SocketFields, "RelicStoneSocket" { shape: "ShapeKindId", stone: "StoneId" });
offsets!(StoneFields, "RelicStone" { id: "Id", type_id: "TypeId" });
offsets!(DataFields, "UserRelicData" {
    relics: "Relics", by_hero: "RelicDataByHeroId", stones: "Stones",
});

#[derive(Serialize)]
pub struct Relic {
    pub id: i32,
    pub type_id: i32,
    pub rank: i32,
    pub level: i32,
    pub sockets: Vec<Socket>,
}

#[derive(Serialize)]
pub struct Socket {
    /// `RelicStoneShapeKindId`
    pub shape: i32,
    /// the stone in it (a `Stone`'s id), if any
    pub stone: Option<i32>,
}

#[derive(Serialize)]
pub struct Stone {
    pub id: i32,
    pub type_id: i32,
}

pub type Worn = BTreeMap<i32, Vec<i32>>;

pub fn read(
    process: &Process,
    layout: &Layout,
    user: u64,
) -> Result<(Vec<Relic>, Worn, Vec<Stone>), String> {
    let relic = RelicFields::new(layout)?;
    let socket = SocketFields::new(layout)?;
    let stone = StoneFields::new(layout)?;
    let data = DataFields::new(layout)?;
    let ids = layout.field("HeroRelicData.RelicIds")?;
    let d = process.block(layout.follow(process, user, &PATH)?, data.span)?;

    let relics = list_refs(process, d.ptr(data.relics))?
        .into_iter()
        .map(|addr| {
            let b = process.block(addr, relic.span)?;
            let sockets = match b.ptr(relic.sockets) {
                0 => Vec::new(),
                list => list_refs(process, list)?
                    .into_iter()
                    .map(|s| {
                        let sb = process.block(s, socket.span)?;
                        Ok(Socket { shape: sb.i32(socket.shape), stone: sb.nullable_i32(socket.stone) })
                    })
                    .collect::<Result<_, String>>()?,
            };
            Ok(Relic {
                id: b.i32(relic.id),
                type_id: b.i32(relic.type_id),
                rank: b.i32(relic.rank),
                level: b.i32(relic.level),
                sockets,
            })
        })
        .collect::<Result<_, String>>()?;
    let worn = dict_refs(process, d.ptr(data.by_hero))?
        .into_iter()
        .map(|(hero, data)| Ok((hero, list_i32(process, process.read(data + ids)?)?)))
        .collect::<Result<_, String>>()?;

    let stones = match d.ptr(data.stones) {
        0 => Vec::new(),
        list => list_refs(process, list)?
            .into_iter()
            .map(|s| {
                let b = process.block(s, stone.span)?;
                Ok(Stone { id: b.i32(stone.id), type_id: b.i32(stone.type_id) })
            })
            .collect::<Result<_, String>>()?,
    };

    Ok((relics, worn, stones))
}
