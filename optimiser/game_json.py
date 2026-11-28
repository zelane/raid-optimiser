"""
game_json.py - the game's JSON as named data: its short `[Json]` keys named, enums by name and
text keys by their default text, by a schema `tools.gen_schema` writes from the dump's
attributes (`schema/events.json` for the events the reader keeps whole).

- `decode`: a value as a C# type
- `decode_key`, `type_arguments`: its steps
"""

from typing import Any


def decode(value: Any, type_name: str, schema: dict) -> Any:
    """`value` as the C# type `type_name`: classes' short keys named, enums by name, a text key
    by its default text; what the schema doesn't know is kept as it is."""
    type_name = type_name.removesuffix("?")
    classes, enums = schema["classes"], schema["enums"]

    match type_name:
        case _ if value is None:
            return None

        case _ if type_name.startswith("Nullable<"):
            return decode(value, type_name[len("Nullable<") : -1], schema)

        case _ if type_name.endswith("[]") and isinstance(value, list):
            return [decode(item, type_name[:-2], schema) for item in value]

        case _ if type_name.startswith("List<") and isinstance(value, list):
            return [decode(item, type_name[len("List<") : -1], schema) for item in value]

        case _ if type_name.startswith("Dictionary<") and isinstance(value, dict):
            key_type, value_type = type_arguments(type_name)
            return {
                decode_key(key, key_type, enums): decode(item, value_type, schema)
                for key, item in value.items()
            }

        case "SharedLTextKey" if isinstance(value, dict):
            return value.get("d")

        case _ if (short := type_name.split(".")[-1]) in enums:
            return enums[short].get(str(value), value)

        case _ if short in classes and isinstance(value, dict):
            fields = classes[short]
            return {
                fields[key]["name"]: decode(item, fields[key]["type"], schema)
                for key, item in value.items()
                if key in fields
            }

    return value


def decode_key(key: str, type_name: str, enums: dict) -> str:
    """A dictionary's key: an enum's by name, any other as the text it came as."""
    short = type_name.split(".")[-1]
    return enums[short].get(key, key) if short in enums else key


def type_arguments(generic: str) -> tuple[str, str]:
    """A two-argument generic's arguments: `Dictionary<int, List<int>>` → int, List<int>."""
    inner = generic[generic.index("<") + 1 : -1]
    depth = 0

    for index, char in enumerate(inner):
        depth += {"<": 1, ">": -1}.get(char, 0)

        if char == "," and depth == 0:
            return inner[:index].strip(), inner[index + 1 :].strip()

    raise ValueError(f"not a two-argument generic: {generic}")
