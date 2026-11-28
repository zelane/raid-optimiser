//! Events and tournaments. The game keeps what's on (each event: its dates, how it scores, its
//! rewards) as its own JSON, `UserWrapper.GlobalEvents.DataJson`, written as read
//! (`optimiser.events` decodes it). How far the account has got in each is in its quests:
//! `UserWrapper.Quests.QuestData.OpenedStates`, an event's quest's completions holding its
//! points (`BySoloEvent`: each action's, `EventsProgress`, summed; its `ByPoints` stays 0)
//! or its rating (`ByTournament`'s `GlobalRatingInfo`).
//!
//! The events' own texts (titles, descriptions: what the JSON's interface settings name by id)
//! come from the server in the player's language, kept apart:
//! `AppModel.GlobalEventsExternalLocalizationStorage._storage`.
//!
//! - `Events`: the game's JSON, the texts, the account's progress and its summons
//!   (`summons`)
//! - `Progress`: one event's, by its quest
//! - `read`: both (warns, and reads nothing, if the game has none loaded)

use serde::Serialize;

use std::collections::BTreeMap;

use crate::collections::{concurrent_dict_refs, list_refs, long_string};
use crate::layout::{offsets, Layout};
use crate::process::Process;
use crate::summons::{self, Summons};

/// Far beyond the ~130 KB the game holds, so a bad read can't ask for gigabytes
const JSON_MAX: i32 = 16 * 1024 * 1024;
/// An event's description runs to a few paragraphs at most
const TEXT_MAX: i32 = 64 * 1024;

offsets!(StateFields, "QuestState" {
    quest: "QuestId", prototype: "PrototypeId", state: "StateId", completions: "Completions",
});
offsets!(CompletionFields, "QuestCompletion" {
    solo: "BySoloEvent", tournament: "ByTournament",
});
offsets!(SoloFields, "QuestCompletionBySoloEvent" { bracket: "BracketIndex", log: "EventsProgress" });
offsets!(RatingFields, "GlobalRatingInfo" {
    points: "Points", position: "Position", global_position: "GlobalPosition",
    bracket: "BracketIndex",
});

#[derive(Serialize)]
pub struct Events {
    /// `UpdatableGlobalEventsData` in the game's JSON (its short keys)
    pub json: String,
    /// text id → the text, in the game's language
    pub texts: BTreeMap<i32, String>,
    pub progress: Vec<Progress>,
    /// shards, mercy and summon boosts, for what opening shards would earn (None if they
    /// couldn't be read: the events are still worth writing)
    pub summons: Option<Summons>,
}

#[derive(Serialize)]
pub struct Progress {
    pub quest_id: i32,
    /// the event's quest's prototype id (an event's quest in the JSON, `QuestData.q.i`)
    pub prototype_id: i32,
    /// `QuestStateId`: New, InProgress, Completed
    pub state: String,
    pub points: i64,
    /// a tournament's place in its bracket and overall, as the server last sent them
    pub position: Option<i64>,
    pub global_position: Option<i64>,
    pub bracket: Option<i32>,
}

pub fn read(
    process: &Process,
    layout: &Layout,
    app: u64,
    user: u64,
) -> Result<Option<Events>, String> {
    match events(process, layout, app, user) {
        Ok(events) => Ok(Some(events)),
        Err(e) => {
            eprintln!("no events: {e}");
            Ok(None)
        }
    }
}

fn events(process: &Process, layout: &Layout, app: u64, user: u64) -> Result<Events, String> {
    let wrapper = layout.follow(process, user, &["UserWrapper.GlobalEvents"])?;
    let json = process.read(wrapper + layout.field("GlobalEventsWrapperReadOnly.DataJson")?)?;
    let json = long_string(process, json, JSON_MAX)?;

    // Starting up or closing, the game holds no events yet: not a read worth writing.
    if json.is_empty() {
        return Err("the game hasn't loaded its events".into());
    }

    let path = ["UserWrapper.Quests", "QuestWrapperReadOnly.QuestData"];
    let quests = layout.follow(process, user, &path)?;
    let states = process.read(quests + layout.field("UserQuestData.OpenedStates")?)?;
    let reader = Reader::new(layout)?;
    let progress = list_refs(process, states)?
        .into_iter()
        .map(|state| reader.progress(process, layout, state))
        .filter_map(Result::transpose)
        .collect::<Result<_, String>>()?;

    Ok(Events {
        json,
        texts: texts(process, layout, app)?,
        progress,
        summons: summons::read(process, layout, user)
            .inspect_err(|e| eprintln!("summons: {e}"))
            .ok(),
    })
}

fn texts(process: &Process, layout: &Layout, app: u64) -> Result<BTreeMap<i32, String>, String> {
    let path = ["AppModel.GlobalEventsExternalLocalizationStorage"];
    let storage = layout.follow(process, app, &path)?;
    let dict = process.read(storage + layout.field("ExternalStringStorage._storage")?)?;

    concurrent_dict_refs(process, dict)?
        .into_iter()
        .map(|(id, text)| Ok((id, long_string(process, text, TEXT_MAX)?)))
        .collect()
}

struct Reader {
    state: StateFields,
    completion: CompletionFields,
    solo: SoloFields,
    log_points: u64,
    rating_info: u64,
    rating: RatingFields,
}

impl Reader {
    fn new(layout: &Layout) -> Result<Reader, String> {
        Ok(Reader {
            state: StateFields::new(layout)?,
            completion: CompletionFields::new(layout)?,
            solo: SoloFields::new(layout)?,
            log_points: layout.field("GlobalEventActionProgress.Points")?,
            rating_info: layout.field("QuestCompletionByTournament.GlobalRatingInfo")?,
            rating: RatingFields::new(layout)?,
        })
    }

    /// The quest's event progress: its first completion that is an event's (none for
    /// other quests).
    fn progress(
        &self,
        process: &Process,
        layout: &Layout,
        state: u64,
    ) -> Result<Option<Progress>, String> {
        let s = process.block(state, self.state.span)?;

        for completion in list_refs(process, s.ptr(self.state.completions))? {
            let c = process.block(completion, self.completion.span)?;
            let solo = c.ptr(self.completion.solo);
            let tournament = c.ptr(self.completion.tournament);
            let found = if solo != 0 {
                Some(self.solo(process, solo)?)
            } else if tournament != 0 {
                self.tournament(process, tournament)?
            } else {
                None
            };

            if let Some((points, position, global_position, bracket)) = found {
                return Ok(Some(Progress {
                    quest_id: s.i32(self.state.quest),
                    prototype_id: s.i32(self.state.prototype),
                    state: layout.name("QuestStateId", s.i32(self.state.state))?,
                    points,
                    position,
                    global_position,
                    bracket,
                }));
            }
        }

        Ok(None)
    }

    fn solo(&self, process: &Process, solo: u64) -> Result<Standing, String> {
        let b = process.block(solo, self.solo.span)?;
        let points = list_refs(process, b.ptr(self.solo.log))?
            .into_iter()
            .map(|entry| Ok(process.read::<i32>(entry + self.log_points)? as i64))
            .sum::<Result<i64, String>>()?;
        Ok((points, None, None, b.nullable_i32(self.solo.bracket)))
    }

    fn tournament(&self, process: &Process, tournament: u64) -> Result<Option<Standing>, String> {
        let info = process.read::<u64>(tournament + self.rating_info)?;

        if info == 0 {
            return Ok(None);
        }

        let r = process.block(info, self.rating.span + 8)?;
        Ok(Some((
            r.i64(self.rating.points),
            r.nullable_i64(self.rating.position),
            r.nullable_i64(self.rating.global_position),
            r.nullable_i32(self.rating.bracket),
        )))
    }
}

/// points, position, global position, bracket
type Standing = (i64, Option<i64>, Option<i64>, Option<i32>);
