//! raid-reader: reads the account out of the running game's memory, from outside the process
//! (read-only: nothing is injected or written), by the layout `tools.reader_layout` takes
//! from the game's IL2CPP dump. Values are the game's own: ids, and enums by their names
//! (`optimiser.account` parses the file).
//!
//! The events go to a file of their own: they change by the minute, the rest only now and then,
//! so `watch` reads them far more often.
//!
//! - `Snapshot`: everything read but the events, as written
//! - `Outputs`: where the account and the events are written
//! - `read_account`, `read_events`: one pass over each
//! - `to_json`, `write_json`, `write_text`: writing them (whole, or not at all)
//! - `read_once`: both, once
//! - `main`: `raid-reader [--watch] <layout.json> <snapshot.json> <events.json>`
//!
//! It runs in the game's Wine prefix (`just read`, `just watch`), so paths are Windows ones
//! (`Z:\...`).

mod account;
mod artifacts;
mod chimera;
mod collections;
mod events;
mod heroes;
mod il2cpp;
mod layout;
mod process;
mod relics;
mod roots;
mod stages;
mod summons;
mod teams;
mod watch;

use std::collections::BTreeMap;
use std::time::Instant;

use serde::Serialize;

use layout::Layout;
use process::Process;

const EXE: &str = "Raid.exe";
const MODULE: &str = "GameAssembly.dll";

#[derive(Serialize)]
struct Snapshot {
    game_version: String,
    user_id: i64,
    arena_league: Option<String>,
    great_hall: account::GreatHall,
    heroes: Vec<heroes::Hero>,
    /// champion id → the pieces they wear
    equipped: BTreeMap<i32, Vec<i32>>,
    artifacts: Vec<artifacts::Artifact>,
    relics: Vec<relics::Relic>,
    /// champion id → the relics they wear
    worn_relics: relics::Worn,
    inbox: Vec<account::InboxItem>,
    presets: Vec<teams::Preset>,
    gear_presets: Vec<artifacts::GearPreset>,
    arena_defense: Vec<i32>,
    arena3x3_defense: Vec<Vec<i32>>,
    /// per 3v3 team and slot: the champion's skill settings
    arena3x3_priorities: Vec<Vec<Option<teams::SkillPriorities>>>,
    chimera: Option<chimera::Raid>,
    /// stage id → how far the account has got (stages it has fought)
    stages: BTreeMap<i32, stages::Progress>,
}

pub struct Outputs {
    pub snapshot: String,
    pub events: String,
}

fn read_account(process: &Process, layout: &Layout) -> Result<Snapshot, String> {
    let app = roots::app_model(process, layout)?;
    let user = layout.follow(process, app, &["AppModel._userWrapper"])?;
    let reader = artifacts::Reader::new(layout)?;
    let (artifacts, source) = artifacts::read(process, layout, &reader, user)?;
    let (relics, worn_relics) = relics::read(process, layout, user)?;
    eprintln!("{} pieces from {source}", artifacts.len());

    Ok(Snapshot {
        game_version: layout.game_version.clone(),
        user_id: process.read(app + layout.field("AppModel.UserId")?)?,
        arena_league: account::arena_league(process, layout, user)?,
        great_hall: account::great_hall(process, layout, user)?,
        heroes: heroes::read(process, layout, user)?,
        equipped: artifacts::equipped(process, layout, user)?,
        artifacts,
        relics,
        worn_relics,
        inbox: account::inbox(process, layout, &reader, user)?,
        presets: teams::presets(process, layout, user)?,
        gear_presets: artifacts::presets(process, layout)?,
        arena_defense: teams::arena_defense(process, layout, user)?,
        arena3x3_defense: teams::arena3x3_defense(process, layout, user)?,
        arena3x3_priorities: teams::arena3x3_priorities(process, layout, user)?,
        chimera: chimera::read(process, layout)?,
        stages: stages::read(process, layout, user)?,
    })
}

/// What's on, as the game's JSON, and the account's points in each (None if the game has
/// none loaded).
fn read_events(process: &Process, layout: &Layout) -> Result<Option<events::Events>, String> {
    let app = roots::app_model(process, layout)?;
    let user = layout.follow(process, app, &["AppModel._userWrapper"])?;
    events::read(process, layout, app, user)
}

fn to_json<T: Serialize>(value: &T) -> Result<String, String> {
    serde_json::to_string(value).map_err(|e| e.to_string())
}

fn write_json<T: Serialize>(path: &str, value: &T) -> Result<(), String> {
    write_text(path, &to_json(value)?)
}

/// Written whole, then moved over the old file, so the web server never reads half of one.
fn write_text(path: &str, text: &str) -> Result<(), String> {
    let partial = format!("{path}.partial");
    std::fs::write(&partial, text).map_err(|e| format!("{partial}: {e}"))?;
    std::fs::rename(&partial, path).map_err(|e| format!("{path}: {e}"))
}

fn read_once(layout: &Layout, outputs: &Outputs) -> Result<(), String> {
    let process = open()?;
    write_json(&outputs.events, &read_events(&process, layout)?)?;
    write_account(&process, layout, outputs)
}

fn open() -> Result<Process, String> {
    let process = Process::open(EXE, MODULE)?;
    eprintln!(
        "{EXE} pid {}, {MODULE} at {:#x}",
        process.pid, process.module_base
    );
    Ok(process)
}

fn write_account(process: &Process, layout: &Layout, outputs: &Outputs) -> Result<(), String> {
    let started = Instant::now();
    let snapshot = read_account(process, layout)?;
    eprintln!(
        "user {}: {} heroes, {} pieces, {} relics, {} inbox items in {:.2?}",
        snapshot.user_id,
        snapshot.heroes.len(),
        snapshot.artifacts.len(),
        snapshot.relics.len(),
        snapshot.inbox.len(),
        started.elapsed(),
    );

    write_json(&outputs.snapshot, &snapshot)
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let (watching, paths) = match args.split_first() {
        Some((flag, rest)) if flag == "--watch" => (true, rest),
        _ => (false, &args[..]),
    };

    let [layout_path, snapshot, events] = paths else {
        eprintln!("usage: raid-reader [--watch] <layout.json> <snapshot.json> <events.json>");
        std::process::exit(2);
    };
    let outputs = Outputs {
        snapshot: snapshot.clone(),
        events: events.clone(),
    };
    let done = Layout::load(layout_path).and_then(|layout| match watching {
        true => watch::run(&layout, &outputs),
        false => read_once(&layout, &outputs),
    });

    if let Err(e) = done {
        eprintln!("raid-reader: {e}");
        std::process::exit(1);
    }
}
