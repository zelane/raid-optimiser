"""
dump_types.py - the class layouts in an Il2CppDumper dump.cs: each type's fields (with offsets),
methods (with RVAs and vtable slots), constants and initialised-data offsets, by full name.
`tools.game_emulator` builds objects and vtables from them.

Parsing a 56 MB dump.cs takes ~20 s, so `load` keeps the result in data/cache by dump.

- `Field`, `Method`, `TypeDef`: a type's layout
- `load`: the dump's types, cached
- `parse`, `by_full_name`: the parser
"""

import pickle
import re
from dataclasses import dataclass, field
from pathlib import Path

from optimiser.paths import DATA

CACHE = DATA / "cache"
VERSION = 2  # of the parser: a cache made by another is parsed again

HEADER = re.compile(
    r"^(?:\[.*\]\s*)?(?:public|private|internal|protected)[\w ]*? "
    r"(class|struct|enum|interface) (\S+?)(?: : ([^/]+?))? // TypeDefIndex: (\d+)$"
)
MODIFIERS = r"(?:(?:public|private|internal|protected|static|readonly|volatile|new) )*"
FIELD = re.compile(rf"^\t(?:\[.*\] )?({MODIFIERS})(.+) ([\w<>|$.`]+); // 0x([0-9A-F]+)$")
DATA_FIELD = re.compile(r"^\t.* (\w+) /\*Metadata offset 0x([0-9A-F]+)\*/; // 0x[0-9A-F]+$")
CONST = re.compile(r"^\t(?:public|private|internal) const (\S+) (\w+) = (-?\w+);")
RVA = re.compile(r"^\t// RVA: 0x([0-9A-F]+) .*?(?:Slot: (\d+))?$")
METHOD = re.compile(r"^\t(?:\[.*\] )?[\w ]*? ([^\s(]+)\((.*)\) \{ \}$")


@dataclass
class Field:
    name: str
    type: str
    offset: int
    static: bool


@dataclass
class Method:
    name: str
    rva: int
    slot: int | None
    params: str


@dataclass
class TypeDef:
    namespace: str
    name: str  # nested types as Outer.Inner
    kind: str  # class, struct, enum, interface
    base: str | None
    index: int  # TypeDefIndex
    fields: dict[str, Field] = field(default_factory=dict)
    methods: list[Method] = field(default_factory=list)
    consts: dict[str, int] = field(default_factory=dict)
    data: dict[str, int] = field(default_factory=dict)  # initialisers' global-metadata offsets

    @property
    def full_name(self) -> str:
        return f"{self.namespace}.{self.name}" if self.namespace else self.name


def load(dump_cs: Path) -> dict[str, TypeDef]:
    """The dump's types, from the cache when it was made from this dump.cs."""
    stat = dump_cs.stat()
    cache = (
        CACHE
        / f"dump-types-v{VERSION}-{dump_cs.parent.name}-{stat.st_size}-{int(stat.st_mtime)}.pickle"
    )
    if cache.exists():
        return pickle.loads(cache.read_bytes())

    types = parse(dump_cs)
    CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(pickle.dumps(types))
    return types


def parse(dump_cs: Path) -> dict[str, TypeDef]:
    parsed: list[TypeDef] = []
    namespace = ""
    current: TypeDef | None = None
    pending_rva: tuple[int, int | None] | None = None

    for line in open(dump_cs, encoding="utf-8", errors="replace"):
        line = line.rstrip("\n")
        if line.startswith("// Namespace: "):
            namespace = line.removeprefix("// Namespace: ")
            continue

        if header := HEADER.match(line):
            kind, name, base, index = header.groups()
            base = base.split(",")[0].strip() if base else None
            current = TypeDef(namespace, name, kind, base, int(index))
            parsed.append(current)
            continue

        if current is None:
            continue

        if line == "}":
            current = None
        elif data := DATA_FIELD.match(line):
            current.data[data[1]] = int(data[2], 16)
        elif (const := CONST.match(line)) and const[3].lstrip("-").isdigit():
            current.consts[const[2]] = int(const[3])
        elif member := FIELD.match(line):
            modifiers, type_, name, offset = member.groups()
            current.fields[name] = Field(name, type_, int(offset, 16), "static" in modifiers)
        elif rva := RVA.match(line):
            pending_rva = (int(rva[1], 16), int(rva[2]) if rva[2] else None)
        elif pending_rva and (method := METHOD.match(line)):
            current.methods.append(Method(method[1], *pending_rva, method[2]))
            pending_rva = None

    return by_full_name(parsed)


def by_full_name(parsed: list[TypeDef]) -> dict[str, TypeDef]:
    """Key the types by full name. A nested type printed without a namespace takes its outer
    type's (the outer type nearest it by TypeDefIndex); the assemblies' several
    `<PrivateImplementationDetails>` pool their data."""
    outers: dict[str, list[TypeDef]] = {}

    for type_def in parsed:
        outers.setdefault(type_def.name, []).append(type_def)

    types: dict[str, TypeDef] = {}

    for type_def in parsed:
        if not type_def.namespace and "." in type_def.name:
            if candidates := outers.get(type_def.name.split(".")[0]):
                type_def.namespace = min(
                    candidates, key=lambda o: abs(o.index - type_def.index)
                ).namespace

        kept = types.setdefault(type_def.full_name, type_def)
        if kept is not type_def:
            kept.data.update(type_def.data)

    return types
