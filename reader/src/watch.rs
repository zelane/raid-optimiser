//! Watching the game: keeps both files current while it runs, at little cost while nothing
//! changes, and rewrites a file only when what it holds has changed (the web server reparses
//! what it's handed).
//!
//! The events (~25 ms) are read every poll. The account (~2.5 s, nearly all of it the gear)
//! is read once its fingerprint has moved and then stood still for `QUIET`: a run of
//! auto-battles moves it every fight, and the account is only worth reading once they stop.
//! The fingerprint is the account's power, experience, the resources it has spent and the
//! silver it has gained (`UserAccount`): a battle, an upgrade, an equip, a sale each move one
//! of them, a dozen small reads. Not the other resources gained: some accrue by the second
//! (regenerating currencies, in fractions). Nor `ServerTimeManager._lastServerTime`, stamped
//! on every server response: the client's periodic requests move it about twice every 30 s.
//!
//! A failed read (the game loading, a collection changing mid-read) is retried at the next
//! poll; when the game closes, it waits for the next one.
//!
//! - `POLL`, `QUIET`, `REOPEN`: how often it looks, how long the fingerprint stands still
//!   before the account is read, how often it looks for a game to open
//! - `run`: watch until stopped
//! - `Written`: what each file last got
//! - `watch_game`, `fingerprint`, `resources`: one game's lifetime, and what says the account
//!   changed

use std::thread::sleep;
use std::time::{Duration, Instant};

use crate::collections::dict_refs;
use crate::layout::{offsets, Layout};
use crate::process::Process;
use crate::{open, read_account, read_events, roots, to_json, write_text, Outputs};

const POLL: Duration = Duration::from_secs(5);
const QUIET: Duration = Duration::from_secs(20);
const REOPEN: Duration = Duration::from_secs(15);
const SILVER: &str = "Silver"; // the only resource gained the fingerprint counts

offsets!(AccountFields, "UserAccount" {
    power: "TotalPower", experience: "Experience", gained: "ResourcesGained",
    spent: "ResourcesSpent",
});

pub fn run(layout: &Layout, outputs: &Outputs) -> Result<(), String> {
    let mut written = Written::default();

    loop {
        match open() {
            Ok(process) => watch_game(&process, layout, outputs, &mut written),
            Err(e) => eprintln!("waiting for the game: {e}"),
        }

        sleep(REOPEN);
    }
}

/// The JSON each file was last written with, so an unchanged read isn't written again.
#[derive(Default)]
struct Written {
    events: Option<String>,
    snapshot: Option<String>,
}

/// Until the game closes: the events each poll, the account once its fingerprint has moved
/// and settled. Starting counts as a move, so the account is read once it's quiet.
fn watch_game(process: &Process, layout: &Layout, outputs: &Outputs, written: &mut Written) {
    let started = Instant::now();
    let log = |what: &str| eprintln!("{:>6}s {what}", started.elapsed().as_secs());
    let mut seen: Option<Vec<u64>> = None;
    let mut moved_at: Option<Instant> = Some(started); // the account not read since

    while process.alive() {
        match read_events(process, layout).and_then(|events| to_json(&events)) {
            Ok(json) if written.events.as_ref() != Some(&json) => {
                match write_text(&outputs.events, &json) {
                    Ok(()) => log("events changed"),
                    Err(e) => eprintln!("events: {e}"),
                }
                written.events = Some(json);
            }

            Ok(_) => {}
            Err(e) => eprintln!("events: {e}"),
        }

        match fingerprint(process, layout) {
            Ok(now) if seen.as_ref() != Some(&now) => {
                if seen.is_some() {
                    moved_at = Some(Instant::now());
                }
                seen = Some(now);
            }

            Ok(_) => {}
            Err(e) => eprintln!("fingerprint: {e}"),
        }

        if moved_at.is_some_and(|at| at.elapsed() >= QUIET) {
            match read_account(process, layout).and_then(|snapshot| to_json(&snapshot)) {
                Ok(json) if written.snapshot.as_ref() == Some(&json) => moved_at = None,
                Ok(json) => match write_text(&outputs.snapshot, &json) {
                    Ok(()) => {
                        log("account changed");
                        written.snapshot = Some(json);
                        moved_at = None;
                    }
                    Err(e) => eprintln!("account: {e}"),
                },
                Err(e) => eprintln!("account: {e}"),
            }
        }

        sleep(POLL);
    }

    eprintln!("the game closed");
}

/// `UserWrapper.Account.AccountData`: its power and experience (as their bits), the silver it
/// has gained, then each resource it has spent, by kind (a `Dictionary<ResourceTypeId,
/// double>`, whose entries `dict_refs` reads as it would a reference's: the double's 8 bytes).
fn fingerprint(process: &Process, layout: &Layout) -> Result<Vec<u64>, String> {
    let fields = AccountFields::new(layout)?;
    let app = roots::app_model(process, layout)?;
    let path = [
        "AppModel._userWrapper",
        "UserWrapper.Account",
        "AccountWrapperReadOnly.AccountData",
    ];
    let account = process.block(layout.follow(process, app, &path)?, fields.span)?;
    let silver = resources(process, layout, account.ptr(fields.gained))?
        .into_iter()
        .filter(|&(kind, _)| {
            layout
                .name("ResourceTypeId", kind)
                .is_ok_and(|n| n == SILVER)
        });
    let spent = resources(process, layout, account.ptr(fields.spent))?;

    Ok([account.ptr(fields.power), account.ptr(fields.experience)]
        .into_iter()
        .chain(
            silver
                .chain(spent)
                .flat_map(|(kind, bits)| [kind as u64, bits]),
        )
        .collect())
}

/// A `Resources`' amounts by kind (as the doubles' bits), in kind order; none if it's null.
fn resources(
    process: &Process,
    layout: &Layout,
    resources: u64,
) -> Result<Vec<(i32, u64)>, String> {
    if resources == 0 {
        return Ok(Vec::new());
    }

    let values = process.read::<u64>(resources + layout.field("Resources.RawValues")?)?;
    let mut by_kind = dict_refs(process, values)?;
    by_kind.sort_unstable();
    Ok(by_kind)
}
