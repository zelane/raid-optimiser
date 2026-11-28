"""
static_convert.py - the game's static data as named, typed values: its short MessagePack keys
named and its values typed by the schema `tools.gen_schema` writes from the dump
(`schema/schema.json`): enums by name, Fixed as numbers, lists and dictionaries by their
element types. `tools.static_export` runs it over the whole file.

- `Converter`: the conversion, noting keys and enum values the schema doesn't know
- `split_args`: a generic's type arguments
"""

import re
from collections import Counter

FIXED_ONE = 2**32  # SharedModel Fixed is 32.32 fixed point


PRIMITIVES = {
    "int",
    "uint",
    "long",
    "ulong",
    "short",
    "ushort",
    "byte",
    "sbyte",
    "double",
    "float",
    "bool",
    "string",
    "decimal",
    "Int32",
    "Int64",
}


LIST_RE = re.compile(
    r"^(?:List|IReadOnlyList|IList|IEnumerable|HashSet|IReadOnlyCollection|ICollection)<(.+)>$"
)


def split_args(s):
    depth, cur, out = 0, "", []
    for ch in s:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    return out + [cur.strip()]


class Converter:
    def __init__(self, schema, strings):
        self.classes, self.enums, self.strings = schema["classes"], schema["enums"], strings
        self.unknown_keys = Counter()  # (class, key) present in data, absent from schema
        self.enum_misses = Counter()  # (enum, value) not in schema
        self.unresolved_text = 0

    def conv(self, v, t):
        if v is None:
            return None
        t = t.strip().replace("System.", "")
        if t.endswith("?"):
            t = t[:-1]
        if t.startswith("Nullable<"):
            return self.conv(v, t[9:-1])
        if t.endswith("[]"):
            return [self.conv(x, t[:-2]) for x in v] if isinstance(v, list) else v
        m = LIST_RE.match(t)
        if m:
            return [self.conv(x, m.group(1)) for x in v] if isinstance(v, list) else v
        if t.startswith(
            ("Dictionary<", "IReadOnlyDictionary<", "SortedDictionary<")
        ) and isinstance(v, dict):
            kt, vt = split_args(t[t.index("<") + 1 : -1])
            return {str(self.conv_key(k, kt)): self.conv(x, vt) for k, x in v.items()}
        short = t.split(".")[-1]
        if short in PRIMITIVES:
            return v
        if short == "Fixed":
            return v / FIXED_ONE if isinstance(v, (int, float)) else v
        if short == "SharedLTextKey" and isinstance(v, dict):
            text = self.strings.get(v.get("k")) or v.get("d")
            if not text or text.startswith("l10n:"):
                self.unresolved_text += 1
            return text
        if short in self.enums:
            return self.enum_name(short, v)
        cls = self.classes.get(short)
        if cls is not None and isinstance(v, dict):
            out = {}
            for k, x in v.items():
                f = cls.get(k)
                if f is None:
                    self.unknown_keys[(short, k)] += 1
                    out["?" + k] = x
                else:
                    out[f["name"]] = self.conv(x, f["type"])
            return out
        return v  # unknown/polymorphic type: keep raw

    def conv_key(self, k, kt):
        short = kt.split(".")[-1]
        if short in self.enums:
            return self.enum_name(short, int(k) if str(k).lstrip("-").isdigit() else k)
        return k

    def enum_name(self, enum, v):
        name = self.enums[enum].get(str(v))
        if name is None:
            self.enum_misses[(enum, v)] += 1
            return v
        return name
