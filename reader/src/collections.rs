//! .NET's collections and strings as IL2CPP lays them out (the dump shows generic types'
//! offsets as 0x0). A null collection reads as empty, a null string as "".
//!
//! - `list_refs`, `list_i32`: a `List<T>`'s items, of a reference `T` or an int
//! - `array_i32`: an `int[]` (or an array of int-sized enums, or pairs of them, flattened)
//! - `string`, `long_string`: a `System.String` (a name; JSON)
//! - `dict_refs`, `dict_i32`: a `Dictionary<K, V>`'s live entries, with an int-sized key
//!   (int or enum) and a reference or int value
//! - `concurrent_dict_refs`: a `ConcurrentDictionary<int, V>`'s entries, of a reference `V`

use crate::process::Process;

const ARRAY_LENGTH: u64 = 0x18;
const ARRAY_DATA: u64 = 0x20;

const STRING_LENGTH: u64 = 0x10;
const STRING_CHARS: u64 = 0x14;
/// Longer than any name the game lets a player type, so a bad read can't ask for gigabytes
const STRING_MAX: i32 = 4096;

const LIST_ITEMS: u64 = 0x10;
const LIST_SIZE: u64 = 0x18;

const DICT_ENTRIES: u64 = 0x18;
const DICT_COUNT: u64 = 0x20;

/// Entry<K, V>: hashCode, next (free entries have it below -1), key, value.
struct Entry {
    size: usize,
    value: usize,
}

const ENTRY_NEXT: usize = 0x4;
const ENTRY_KEY: usize = 0x8;
const REF_ENTRY: Entry = Entry {
    size: 0x18,
    value: 0x10,
};
const INT_ENTRY: Entry = Entry {
    size: 0x10,
    value: 0xC,
};

pub fn list_refs(process: &Process, list: u64) -> Result<Vec<u64>, String> {
    Ok(list_bytes(process, list, 8)?
        .chunks_exact(8)
        .map(|c| u64_at(c, 0))
        .collect())
}

pub fn list_i32(process: &Process, list: u64) -> Result<Vec<i32>, String> {
    Ok(list_bytes(process, list, 4)?
        .chunks_exact(4)
        .map(|c| i32_at(c, 0))
        .collect())
}

/// `ConcurrentDictionary<int, V>` → its `Tables` → their `Node[]` buckets, each a chain of
/// nodes (key, value, next).
const CONCURRENT_TABLES: u64 = 0x10;
const TABLES_BUCKETS: u64 = 0x10;
const NODE_KEY: u64 = 0x10;
const NODE_VALUE: u64 = 0x18;
const NODE_NEXT: u64 = 0x20;

pub fn concurrent_dict_refs(process: &Process, dict: u64) -> Result<Vec<(i32, u64)>, String> {
    if dict == 0 {
        return Ok(Vec::new());
    }

    let tables = process.ptr(dict + CONCURRENT_TABLES, "concurrent dictionary tables")?;
    let buckets = process.ptr(tables + TABLES_BUCKETS, "concurrent dictionary buckets")?;
    let length = process.read::<u64>(buckets + ARRAY_LENGTH)? as usize;
    let heads = array_bytes(process, buckets, length, 8)?;
    let mut entries = Vec::new();

    for head in heads.chunks_exact(8).map(|c| u64_at(c, 0)) {
        let mut node = head;

        while node != 0 {
            let key = process.read::<i32>(node + NODE_KEY)?;
            entries.push((key, process.read::<u64>(node + NODE_VALUE)?));
            node = process.read::<u64>(node + NODE_NEXT)?;
        }
    }

    Ok(entries)
}

pub fn dict_refs(process: &Process, dict: u64) -> Result<Vec<(i32, u64)>, String> {
    let entries = live_entries(process, dict, &REF_ENTRY)?;
    Ok(entries
        .iter()
        .map(|e| (i32_at(e, ENTRY_KEY), u64_at(e, REF_ENTRY.value)))
        .collect())
}

pub fn dict_i32(process: &Process, dict: u64) -> Result<Vec<(i32, i32)>, String> {
    let entries = live_entries(process, dict, &INT_ENTRY)?;
    Ok(entries
        .iter()
        .map(|e| (i32_at(e, ENTRY_KEY), i32_at(e, INT_ENTRY.value)))
        .collect())
}

/// Every int in the array; `per_item` ints per element (2 for a `ValueTuple<int, int>`).
pub fn array_i32(process: &Process, array: u64, per_item: usize) -> Result<Vec<i32>, String> {
    if array == 0 {
        return Ok(Vec::new());
    }

    let length = process.read::<u64>(array + ARRAY_LENGTH)? as usize;
    let bytes = array_bytes(process, array, length, 4 * per_item)?;
    Ok(bytes.chunks_exact(4).map(|c| i32_at(c, 0)).collect())
}

pub fn string(process: &Process, string: u64) -> Result<String, String> {
    long_string(process, string, STRING_MAX)
}

/// A `System.String` of at most `max` chars: JSON the game keeps whole, say.
pub fn long_string(process: &Process, string: u64, max: i32) -> Result<String, String> {
    if string == 0 {
        return Ok(String::new());
    }

    let length = process.read::<i32>(string + STRING_LENGTH)?;

    if !(0..=max).contains(&length) {
        return Err(format!("string of length {length} at {string:#x}"));
    }

    let mut bytes = vec![0u8; 2 * length as usize];
    process.read_bytes(string + STRING_CHARS, &mut bytes)?;
    let units: Vec<u16> = bytes
        .chunks_exact(2)
        .map(|c| u16::from_le_bytes([c[0], c[1]]))
        .collect();
    Ok(String::from_utf16_lossy(&units))
}

fn list_bytes(process: &Process, list: u64, item: usize) -> Result<Vec<u8>, String> {
    if list == 0 {
        return Ok(Vec::new());
    }

    let items = process.ptr(list + LIST_ITEMS, "list items")?;
    let size = process.read::<i32>(list + LIST_SIZE)?.max(0) as usize;
    array_bytes(process, items, size, item)
}

fn live_entries(process: &Process, dict: u64, entry: &Entry) -> Result<Vec<Vec<u8>>, String> {
    if dict == 0 {
        return Ok(Vec::new());
    }

    let count = process.read::<i32>(dict + DICT_COUNT)?.max(0) as usize;

    if count == 0 {
        return Ok(Vec::new());
    }

    let entries = process.ptr(dict + DICT_ENTRIES, "dictionary entries")?;
    let bytes = array_bytes(process, entries, count, entry.size)?;

    Ok(bytes
        .chunks_exact(entry.size)
        .filter(|e| i32_at(e, ENTRY_NEXT) >= -1)
        .map(<[u8]>::to_vec)
        .collect())
}

/// The first `count` items of an array, checked against its length (a count beyond it means
/// the game changed the collection mid-read).
fn array_bytes(
    process: &Process,
    array: u64,
    count: usize,
    item: usize,
) -> Result<Vec<u8>, String> {
    let length = process.read::<u64>(array + ARRAY_LENGTH)? as usize;

    if count > length {
        return Err(format!(
            "collection of {count} beyond its array of {length} (mid-update?)"
        ));
    }

    let mut bytes = vec![0u8; count * item];
    process.read_bytes(array + ARRAY_DATA, &mut bytes)?;
    Ok(bytes)
}

fn i32_at(bytes: &[u8], offset: usize) -> i32 {
    i32::from_le_bytes(bytes[offset..][..4].try_into().unwrap())
}

fn u64_at(bytes: &[u8], offset: usize) -> u64 {
    u64::from_le_bytes(bytes[offset..][..8].try_into().unwrap())
}
