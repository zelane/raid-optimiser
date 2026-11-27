"""Generate a schema from an Il2CppDumper dump.cs.

Extracts, for every type reachable from the root classes (`StaticData` by default):
  - serialized keys -> field name + C# type (incl. inherited fields): MessagePack's `[Key]`
    by default, or the game's own JSON's `[Json]` (`--attribute Json`)
  - enum value -> name tables
so the raw data can be renamed and typed: the static data by static_export.py, the events
the reader takes as the game's JSON (`--root UpdatableGlobalEventsData --root
GlobalEventInterfaceSettingsDto --attribute Json`: the second is JSON within it) by
`optimiser.events`.

Re-run after re-dumping the game (`just update` does both):
    uv run python -m tools.gen_schema data/dump/<version>/dump.cs schema/schema.json
"""

import json
import re
from collections import defaultdict

import click

NS_RE = re.compile(r"^// Namespace: ?(.*)$")
TYPE_RE = re.compile(
    r"^(?:public|internal|private|protected)?\s*(?:static |sealed |abstract |readonly )*"
    r"(class|struct|enum) ([\w.`<>,]+?)(?: : ([^/{]+?))?\s*// TypeDefIndex"
)


def key_patterns(attribute):
    """The lines naming a field's serialized key: by string, or by number."""
    return (
        re.compile(rf'^\s*\[{attribute}\("([^"]*)"\)\]'),
        re.compile(rf"^\s*\[{attribute}\((\d+)\)\]"),
    )


FIELD_RE = re.compile(
    r"^\s+(?:public|internal|private|protected)\s+(?:readonly\s+)?(?!const\b|static\b)"
    r"([\w.<>,\[\] ?]+?)\s+(\w+)(?:;| \{)"
)
ENUM_RE = re.compile(r"^\s+public const ([\w.]+) (\w+) = (-?\d+);")


def parse(path, attribute="Key"):
    key_re, intkey_re = key_patterns(attribute)
    types = defaultdict(list)  # short name -> [entry]
    ns, cur, key = "", None, None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = NS_RE.match(line)
            if m:
                ns = m.group(1)
                continue
            m = TYPE_RE.match(line)
            if m:
                kind, name, bases = m.groups()
                cur = {
                    "kind": kind,
                    "name": name,
                    "ns": ns,
                    "bases": [b.strip() for b in (bases or "").split(",") if b.strip()],
                    "fields": [],
                    "values": {},
                }
                types[name.split(".")[-1]].append(cur)
                key = None
                continue
            if cur is None:
                continue
            if cur["kind"] == "enum":
                m = ENUM_RE.match(line)
                if m:
                    cur["values"][m.group(3)] = m.group(2)
                continue
            m = key_re.match(line) or intkey_re.match(line)
            if m:
                key = m.group(1)
                continue
            m = FIELD_RE.match(line)
            if m and key is not None:
                cur["fields"].append({"key": key, "name": m.group(2), "type": m.group(1).strip()})
                key = None
            elif line.strip() and not line.strip().startswith(("[", "//")):
                key = None
    return types


def pick(cands):
    """Several types can share a short name; prefer serializable SharedModel ones."""

    def score(t):
        return (
            bool(t["fields"]) or bool(t["values"]),
            t["ns"].startswith("SharedModel"),
            len(t["fields"]),
        )

    return max(cands, key=score)


GENERIC_RE = re.compile(r"[\w.]+")


def referenced(type_str):
    return [t.split(".")[-1] for t in GENERIC_RE.findall(type_str)]


@click.command(help=__doc__)
@click.argument("dump", type=click.Path(exists=True, dir_okay=False))
@click.argument("out", type=click.Path(dir_okay=False))
@click.option(
    "--root", "roots", multiple=True, default=("StaticData",), help="a class the schema starts from"
)
@click.option("--attribute", default="Key", help="the attribute naming serialized keys")
def main(dump: str, out: str, roots: tuple[str, ...], attribute: str) -> None:
    types = parse(dump, attribute)
    schema = {"classes": {}, "enums": {}}
    todo, seen = list(roots), set()
    while todo:
        n = todo.pop()
        if n in seen or n not in types:
            continue
        seen.add(n)
        t = pick(types[n])
        if t["kind"] == "enum":
            schema["enums"][n] = t["values"]
            continue
        fields = list(t["fields"])
        for b in t["bases"]:  # inherited serialized fields
            bn = b.split("<")[0].split(".")[-1]
            if bn in types:
                fields = pick(types[bn])["fields"] + fields
                todo.extend(referenced(b))
        if not fields:
            continue
        schema["classes"][n] = {f["key"]: {"name": f["name"], "type": f["type"]} for f in fields}
        for f in fields:
            todo.extend(referenced(f["type"]))
    with open(out, "w") as f:
        json.dump(schema, f, indent=1, sort_keys=True)
    print(f"{len(schema['classes'])} classes, {len(schema['enums'])} enums -> {out}")


if __name__ == "__main__":
    main()
