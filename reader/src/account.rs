//! Account-wide state: the Great Hall, the arena league and the inbox.
//!
//! - `great_hall`: affinity → stat → level
//! - `arena_league`: the league, when the game has it
//! - `InboxItem`, `inbox`: inbox items and the pieces they hold (overflow waits there)

use std::collections::BTreeMap;

use serde::Serialize;

use crate::artifacts::{self, Artifact};
use crate::collections::{dict_i32, dict_refs, list_refs};
use crate::layout::{offsets, Layout};
use crate::process::Process;

offsets!(ItemFields, "InboxItem" { id: "Id", type_id: "TypeId", prize: "Prize" });

#[derive(Serialize)]
pub struct InboxItem {
    pub id: i32,
    pub type_id: String,
    pub artifacts: Vec<Artifact>,
}

pub type GreatHall = BTreeMap<String, BTreeMap<String, i32>>;

pub fn great_hall(process: &Process, layout: &Layout, user: u64) -> Result<GreatHall, String> {
    let path = ["UserWrapper.Village", "VillageWrapperReadOnly.VillageData"];
    let data = layout.follow(process, user, &path)?;
    let levels =
        process.read(data + layout.field("UserVillageData.CapitolBonusLevelByStatByElement")?)?;

    dict_refs(process, levels)?
        .into_iter()
        .map(|(element, by_stat)| {
            let levels = dict_i32(process, by_stat)?
                .into_iter()
                .map(|(stat, level)| Ok((layout.name("StatKindId", stat)?, level)))
                .collect::<Result<_, String>>()?;
            Ok((layout.name("Element", element)?, levels))
        })
        .collect()
}

pub fn arena_league(
    process: &Process,
    layout: &Layout,
    user: u64,
) -> Result<Option<String>, String> {
    let arena = layout.follow(process, user, &["UserWrapper.Arena"])?;
    let league = process.block(arena + layout.field("ArenaWrapperReadOnly.LeagueId")?, 8)?;
    league
        .nullable_i32(0)
        .map(|id| layout.name("ArenaLeagueId", id))
        .transpose()
}

pub fn inbox(
    process: &Process,
    layout: &Layout,
    reader: &artifacts::Reader,
    user: u64,
) -> Result<Vec<InboxItem>, String> {
    let item = ItemFields::new(layout)?;
    let prize_artifacts = layout.field("UserPrize.Artifacts")?;
    let data = layout.follow(
        process,
        user,
        &["UserWrapper.Inbox", "InboxWrapperReadOnly.InboxData"],
    )?;
    let items = process.read(data + layout.field("UserInboxData.Items")?)?;

    list_refs(process, items)?
        .into_iter()
        .map(|addr| {
            let b = process.block(addr, item.span)?;
            let pieces = match b.ptr(item.prize) {
                0 => Vec::new(),
                prize => list_refs(process, process.read(prize + prize_artifacts)?)?,
            };

            Ok(InboxItem {
                id: b.i32(item.id),
                type_id: layout.name("InboxTypeId", b.i32(item.type_id))?,
                artifacts: pieces
                    .into_iter()
                    .map(|a| reader.artifact(process, a))
                    .collect::<Result<_, _>>()?,
            })
        })
        .collect()
}
