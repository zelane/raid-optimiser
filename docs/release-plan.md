# Open-source release plan

Notes from 2026-11-17 on packaging raid-optimiser for other players, most of them on Windows,
with the HH integration off by default.

## Two pipelines

- **Maintainer** (after each game update): Il2CppDumper → `just schema` / `just reader-layout`.
  Players never run this.
- **Player** (runtime): read memory → decode the static cache → extract assets → serve the UI.
  Players need no dump, Rust, Node or `just`.

## What ships and what's built locally

Code and the maintainer's layout files ship. Plarium's tables and art are always built on the
player's own machine, never redistributed.

| Piece | Where it comes from |
| --- | --- |
| Python app (FastAPI, highspy, UnityPy, msgpack/lz4) | Frozen into the exe |
| Vue front end | Prebuilt `webui/static/dist`, bundled |
| `reader` | Built natively for Windows in CI (`x86_64-pc-windows-msvc`); runs as a plain process, no umu or prefix |
| `schema/schema.json`, `reader-layout.json` | Versioned data files published by the maintainer after each game update |
| `data/game/*.json`, portraits, icons | Built on first run from the player's install (the `just static` and `just assets` logic) |
| HH capture (mitmproxy, `hh_capture.py`) | Not in the default build |

## Recommended route

1. **A CLI entry point that replaces the justfile for players:** `raid-optimiser serve | sync | refresh`.
   - `serve` starts uvicorn and opens the browser.
   - `refresh` re-decodes static data and assets. It can run automatically when the game version
     changes, since the static-data folder is named by version.
2. **A per-user data directory.** Point `optimiser/paths.py` at `%LOCALAPPDATA%\raid-optimiser\`
   instead of the repo's `data/`, and keep the repo-relative path in dev mode.
3. **Find the game install.** Check Plarium Play's default paths and the registry, then
   `LocalLow/Plarium/Raid_ Shadow Legends/static-data`. Let the player override it on the Config page.
4. **Freeze with PyInstaller (onedir) or Nuitka**, bundling `reader.exe` and `dist/` as data. Wrap
   it in an Inno Setup installer, or ship a zip.
5. **Build in GitHub Actions on `windows-latest`:** cargo build, npm build, freeze, attach to a
   Release. Tag each release with the app version and the game version its layout was checked
   against.
6. **Layouts that update on their own.** Game patches move offsets. If the app can fetch a newer
   `reader-layout.json` and schema from the releases, players aren't stuck waiting for a new exe
   after each patch.

## Alternatives

- **A `uv` launcher.** Ship a small launcher that bundles `uv` and runs the locked project. It's
  easier to maintain and updates nearly as easily as a pull. But it downloads Python on first run
  and is less double-click-and-go.
- **Electron or Tauri: overkill.** A local web UI in the player's browser is fine.
- **Linux:** the current umu/prefix route stays as the developer path.

## Disabling the HH integration

- A setting such as `hh_extractor: false` in the store or a config file. When it's off,
  `webui/extractor.py` isn't reached, and the Equip, Preview and Sell buttons are hidden rather
  than greyed out.
- mitmproxy as an optional extra (`raid-optimiser[hh]`), not in the Windows bundle. That also
  avoids installing a CA certificate on players' machines, which is a big trust ask.
- Consider leaving `capture/` out of the public repo entirely. It works by injecting invocations
  into HH's extractor hub as if HH's server sent them, and HH might reasonably object to that
  being distributed, even when it's off by default.
- Without it the app is purely read-only: it reads memory and recommends builds, and the player
  equips by hand. That's a cleaner public story.

## Risks to settle before release

- **Plarium's terms and bans.** An external `ReadProcessMemory` reader is read-only and injects
  nothing. It's still a third-party tool reading the client, and players carry the ban risk: say
  so clearly in the README. Never ship anything from the raider/injection side.
- **Antivirus and SmartScreen.** An unsigned frozen exe that opens another process with VM_READ
  looks exactly like a trainer, and some AVs will flag it. Code signing helps (free for
  open-source projects through SignPath), as do published source, reproducible CI builds and
  checksums.
- **Licence and assets.** Pick a licence for the code (MIT or GPL). State that game data and art
  are extracted locally, never distributed, and are Plarium's property.

## First steps

These are useful even before any packaging exists.

- [ ] CLI entry point (`serve`, `sync`, `refresh`)
- [ ] Configurable data directory in `optimiser/paths.py`
- [ ] HH feature flag, off by default, with the game-command buttons hidden when off
- [ ] Game install discovery on Windows
- [ ] Windows CI build of `reader` and the frozen app
