//! .NET's collections as IL2CPP lays them out (the dump shows generic types' offsets as 0x0).
//! A null collection reads as empty.
//!
//! - `list_refs`, `list_i32`: a `List<T>`'s items, of a reference `T` or an int
//! - `dict_refs`, `dict_i32`: a `Dictionary<K, V>`'s live entries, with an int-sized key
//!   (int or enum) and a reference or int value

use crate::process::Process;

const ARRAY_LENGTH: u64 = 0x18;
const ARRAY_DATA: u64 = 0x20;

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
