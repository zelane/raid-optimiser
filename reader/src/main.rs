//! raid-reader: reads the account out of the running game's memory, from outside the process
//! (read-only: nothing is injected or written), by the layout `tools.reader_layout` takes
//! from the game's IL2CPP dump. Values are the game's own: ids, and enums by their names
//! (`optimiser.account` parses the file).
//!
//! - `Snapshot`: everything read, as written
//! - `read`: one pass over the account
//! - `main`: `raid-reader <layout.json> <out.json>`
//!
//! It runs in the game's Wine prefix (`just read`), so paths are Windows ones (`Z:\...`).

mod account;
mod artifacts;
mod collections;
mod heroes;
mod il2cpp;
mod layout;
mod process;
mod relics;
mod roots;

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
}

fn read(process: &Process, layout: &Layout) -> Result<Snapshot, String> {
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
    })
}

fn run(layout_path: &str, out_path: &str) -> Result<(), String> {
    let layout = Layout::load(layout_path)?;
    let process = Process::open(EXE, MODULE)?;
    eprintln!(
        "{EXE} pid {}, {MODULE} at {:#x}",
        process.pid, process.module_base
    );
    let started = Instant::now();
    let snapshot = read(&process, &layout)?;
    eprintln!(
        "user {}: {} heroes, {} pieces, {} relics, {} inbox items in {:.2?}",
        snapshot.user_id,
        snapshot.heroes.len(),
        snapshot.artifacts.len(),
        snapshot.relics.len(),
        snapshot.inbox.len(),
        started.elapsed(),
    );

    let json = serde_json::to_string(&snapshot).map_err(|e| e.to_string())?;
    std::fs::write(out_path, json).map_err(|e| format!("{out_path}: {e}"))
}

fn main() {
    let args: Vec<String> = std::env::args().collect();

    if args.len() != 3 {
        eprintln!("usage: raid-reader <layout.json> <out.json>");
        std::process::exit(2);
    }

    if let Err(e) = run(&args[1], &args[2]) {
        eprintln!("raid-reader: {e}");
        std::process::exit(1);
    }
}
