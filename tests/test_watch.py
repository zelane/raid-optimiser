"""
test_watch.py - telling the watcher's processes from others by their command lines, as the web
UI finds them to show and stop it (`webui.reader`).

- `test_watcher_processes`: `just watch`, its recipe, the watching reader; not a single read
"""

from webui.reader import is_watcher

READER = "/repo/reader/target/x86_64-pc-windows-gnu/release/raid-reader.exe"


def test_watcher_processes() -> None:
    assert is_watcher(["just", "watch"])
    assert is_watcher(["/usr/bin/just", "reader-run", "--watch"])
    assert is_watcher([READER, "--watch", "Z:/layout.json", "Z:/snapshot.json", "Z:/events.json"])

    assert not is_watcher(["just", "read"])
    assert not is_watcher([READER, "Z:/layout.json", "Z:/snapshot.json", "Z:/events.json"])
    assert not is_watcher(["proton", "runinprefix", READER, "--watch"])
    assert not is_watcher(["vim", "watch"])
