"""static_decode.py - the game's cached static data, decoded: MessagePack-CSharp's Lz4BlockArray
(a MessagePack array of an extension, type 98, holding each block's uncompressed size as a run
of MessagePack ints, then the LZ4 blocks), whose joined blocks are the MessagePack data.

- `LZ4_BLOCK_ARRAY`: the extension type that heads the array
- `newest`: the latest cached file under the cache (`static-data/<game version>/<hash>`)
- `decode`: a file's data as the tables have always been built from it (the earlier C# decoder's
  JSON): map keys as text, whole-number floats as ints (`text_keys`, `whole_numbers`, `plain`)
"""

import io
from pathlib import Path

import lz4.block
import msgpack

LZ4_BLOCK_ARRAY = 98


def newest(cache: Path) -> Path:
    """The most recently written file under the cache; the game version is its folder's name."""
    files = [path for path in cache.rglob("*") if path.is_file()]

    if not files:
        raise FileNotFoundError(f"no cached static data under {cache}")

    return max(files, key=lambda path: path.stat().st_mtime_ns)


def decode(path: Path) -> dict:
    header, *blocks = msgpack.unpackb(path.read_bytes())

    if not isinstance(header, msgpack.ExtType) or header.code != LZ4_BLOCK_ARRAY:
        raise ValueError(f"{path} isn't an Lz4BlockArray (header {header!r:.40})")

    sizes = list(msgpack.Unpacker(io.BytesIO(header.data)))

    if len(sizes) != len(blocks):
        raise ValueError(f"{path}: {len(sizes)} block sizes for {len(blocks)} blocks")

    payload = b"".join(
        lz4.block.decompress(block, uncompressed_size=size)
        for block, size in zip(blocks, sizes, strict=True)
    )
    return msgpack.unpackb(
        payload, strict_map_key=False, object_pairs_hook=text_keys, list_hook=whole_numbers
    )


def text_keys(pairs: list[tuple]) -> dict:
    return {key if isinstance(key, str) else str(key): plain(value) for key, value in pairs}


def whole_numbers(items: list) -> list:
    return [plain(item) for item in items]


def plain(value):
    return int(value) if isinstance(value, float) and value.is_integer() else value
