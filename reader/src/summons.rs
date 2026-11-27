//! Summoning, for what opening shards would earn in an event: the shards the account holds and
//! the server events boosting a shard type's odds. Not its mercy counters: the server keeps
//! them (the client only has the rules, for the drop rates screen; `UserShardData`'s
//! `SummonResults` is the last summon's, not a count).
//!
//! `UserWrapper.Shards.ShardData` (`UserShardData`): `Shards`, each type's count.
//! `UserWrapper.ServerEvents.ServerEventsData`: each event's dates and, for a summon boost,
//! `Shards`: the drop rules standing in for that type's own while it runs.
//!
//! - `Summons`, `Held`, `Boost`, `DropRule`: what's written
//! - `read`: all of it

use serde::Serialize;

use crate::collections::{list_refs, string};
use crate::layout::{offsets, Layout};
use crate::process::Process;

offsets!(ShardFields, "Shard" { type_id: "TypeId", count: "Count" });
offsets!(EventFields, "ServerEvent" {
    type_id: "TypeId", name: "GboName", from: "DateFrom", to: "DateTo", shards: "Shards",
});
offsets!(BoostFields, "ShardsData" { type_id: "TypeId", rules: "DropRules" });
offsets!(RuleFields, "ShardDropRule" {
    rarity: "Rarity", chance: "Chance", step: "ChanceIncreaseOnEachTry",
    after: "ChanceIncreaseSummonNumber",
});

#[derive(Serialize)]
pub struct Summons {
    pub held: Vec<Held>,
    pub boosts: Vec<Boost>,
}

#[derive(Serialize)]
pub struct Held {
    pub shard: String,
    pub count: i32,
}

#[derive(Serialize)]
pub struct Boost {
    pub event: String,
    pub kind: String,
    /// Unix seconds
    pub from: i64,
    pub to: i64,
    pub shard: String,
    pub rules: Vec<DropRule>,
}

/// As the static data's `ShardDropRule`: a rarity's chance, and past `mercy_after` shards
/// without it, `mercy_step` more for each.
#[derive(Serialize)]
pub struct DropRule {
    pub rarity: String,
    pub chance: f64,
    pub mercy_step: Option<f64>,
    pub mercy_after: Option<i32>,
}

pub fn read(process: &Process, layout: &Layout, user: u64) -> Result<Summons, String> {
    let path = ["UserWrapper.Shards", "ShardWrapperReadOnly.ShardData"];
    let data = layout.follow(process, user, &path)?;
    let shards = process.read(data + layout.field("UserShardData.Shards")?)?;

    Ok(Summons {
        held: held(process, layout, shards)?,
        boosts: boosts(process, layout, user)?,
    })
}

fn held(process: &Process, layout: &Layout, shards: u64) -> Result<Vec<Held>, String> {
    let fields = ShardFields::new(layout)?;

    list_refs(process, shards)?
        .into_iter()
        .map(|shard| {
            let b = process.block(shard, fields.span)?;
            Ok(Held {
                shard: layout.name("ShardTypeId", b.i32(fields.type_id))?,
                count: b.i32(fields.count),
            })
        })
        .collect()
}

/// The server events with shard odds of their own (summon boosts).
fn boosts(process: &Process, layout: &Layout, user: u64) -> Result<Vec<Boost>, String> {
    let event = EventFields::new(layout)?;
    let boost = BoostFields::new(layout)?;
    let path = [
        "UserWrapper.ServerEvents",
        "ServerEventsWrapperReadOnly.ServerEventsData",
    ];
    let data = layout.follow(process, user, &path)?;
    let events = process.read(data + layout.field("ServerEventsData.ServerEvents")?)?;
    let mut found = Vec::new();

    for addr in list_refs(process, events)? {
        let e = process.block(addr, event.span)?;

        if e.ptr(event.shards) == 0 {
            continue;
        }

        let b = process.block(e.ptr(event.shards), boost.span)?;
        found.push(Boost {
            event: string(process, e.ptr(event.name))?,
            kind: layout.name("ServerEventTypeId", e.i32(event.type_id))?,
            from: e.unix_seconds(event.from),
            to: e.unix_seconds(event.to),
            shard: layout.name("ShardTypeId", b.i32(boost.type_id))?,
            rules: drop_rules(process, layout, b.ptr(boost.rules))?,
        });
    }

    Ok(found)
}

fn drop_rules(process: &Process, layout: &Layout, rules: u64) -> Result<Vec<DropRule>, String> {
    let fields = RuleFields::new(layout)?;

    list_refs(process, rules)?
        .into_iter()
        .map(|rule| {
            let b = process.block(rule, fields.span + 8)?;
            Ok(DropRule {
                rarity: layout.name("HeroRarity", b.i32(fields.rarity))?,
                chance: b.f64(fields.chance),
                mercy_step: b.nullable_f64(fields.step),
                mercy_after: b.nullable_i32(fields.after),
            })
        })
        .collect()
}
