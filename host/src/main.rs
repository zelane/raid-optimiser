//! raid-host: the game's own battle engine, run outside the game. Loads the installed
//! GameAssembly.dll into this process under plain Wine (a prefix of its own, never the game's),
//! starts il2cpp, loads the game's static data and the server's battle settings, then plays a
//! fight's setup on auto, once per seed, writing each `BattleResult` as the game's JSON.
//! Nothing here talks to the game, its servers or its account. `just fight` runs it.
//!
//! Arguments (Windows paths):
//!   <GameAssembly.dll> <il2cpp_data dir> <LocalLow copy> <static data version> <snapshot.json>
//! then a command:
//!   fight <setup.json> <seeds> <out dir> [first seed]
//!                                          each seed's BattleResult as out/result-<seed>.json,
//!                                          from the first seed (0 when left out) on
//!   build <request.json> <out.json>        champions' slot parts, built by the game (`build`)
//! The LocalLow copy must be a copy (the game's cache loader deletes a cache it fails to load).
//! Seed 0 is the setup's own (a captured fight replays exactly); 1.. are new.
//!
//! - `il2cpp`: the runtime and calls into it
//! - `unity`: the Unity calls answered here
//! - `game`: startup, static data, battle settings, the game's JSON
//! - `fight`: one fight on auto
//! - `build`: the parts of a team's slots the game computes

mod build;
mod fight;
mod game;
mod il2cpp;
mod unity;

use std::path::Path;
use std::time::Instant;

use unity::Answers;

struct Request {
    game_assembly: String,
    data_dir: String,
    local_low: String,
    version: String,
    snapshot: String,
    command: Command,
}

enum Command {
    Fight { setup: String, first: i32, seeds: i32, out_dir: String },
    Build { request: String, out: String },
}

fn main() {
    if let Err(e) = parse(std::env::args().skip(1).collect()).and_then(|request| run(&request)) {
        eprintln!("raid-host: {e}");
        std::process::exit(1);
    }
}

fn run(request: &Request) -> Result<(), String> {
    let answers = Answers {
        persistent_data_path: request.local_low.replace('\\', "/"),
        version: request.version.clone(),
    };
    let il2cpp = il2cpp::start(&request.game_assembly, &request.data_dir, &unity::internal_calls(answers))?;
    game::start(&il2cpp)?;
    game::load_static_data(&il2cpp)?;
    game::set_battle_settings(&il2cpp, &battle_settings(&request.snapshot)?)?;

    match &request.command {
        Command::Fight { setup, first, seeds, out_dir } => {
            fight_seeds(&il2cpp, &read(setup)?, *first..*first + *seeds, out_dir)
        }
        Command::Build { request, out } => write(out, &build::build(&il2cpp, &read(request)?)?),
    }
}

fn fight_seeds(
    il2cpp: &il2cpp::Il2cpp,
    setup: &str,
    seeds: std::ops::Range<i32>,
    out_dir: &str,
) -> Result<(), String> {
    for seed in seeds {
        let started = Instant::now();
        let result = fight::run(il2cpp, setup, (seed > 0).then_some(seed))?;
        write(&Path::new(out_dir).join(format!("result-{seed}.json")).to_string_lossy(), &result)?;
        eprintln!("seed {seed}: {:.1?}", started.elapsed());
    }

    Ok(())
}

/// The reader's copy of the server's battle settings, from the snapshot.
fn battle_settings(snapshot: &str) -> Result<String, String> {
    let account: serde_json::Value = serde_json::from_str(&read(snapshot)?).map_err(|e| e.to_string())?;

    match account.get("battle_settings") {
        Some(settings) if !settings.is_null() => Ok(settings.to_string()),
        _ => Err("the snapshot has no battle_settings (just read, with the game running)".into()),
    }
}

fn read(path: &str) -> Result<String, String> {
    std::fs::read_to_string(path).map_err(|e| format!("{path}: {e}"))
}

fn write(path: &str, text: &str) -> Result<(), String> {
    std::fs::write(path, text).map_err(|e| format!("{path}: {e}"))
}

fn parse(mut args: Vec<String>) -> Result<Request, String> {
    if args.len() < 6 {
        return Err("expected the game's paths, the snapshot and a command (see main.rs)".into());
    }

    let rest = args.split_off(5);
    let [game_assembly, data_dir, local_low, version, snapshot] =
        <[String; 5]>::try_from(args).map_err(|_| "bad arguments".to_string())?;
    let command = match rest.iter().map(String::as_str).collect::<Vec<_>>().as_slice() {
        ["fight", setup, seeds, out_dir, first @ ..] => Command::Fight {
            setup: setup.to_string(),
            first: match first {
                [] => 0,
                [first] => first.parse().map_err(|_| format!("first seed: {first}"))?,
                _ => return Err("fight takes at most one first seed".into()),
            },
            seeds: seeds.parse().map_err(|_| format!("seeds: {seeds}"))?,
            out_dir: out_dir.to_string(),
        },
        ["build", request, out] => Command::Build { request: request.to_string(), out: out.to_string() },
        other => return Err(format!("unknown command {other:?} (fight or build)")),
    };

    Ok(Request { game_assembly, data_dir, local_low, version, snapshot, command })
}
