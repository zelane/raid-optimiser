//! The game's type layout, from `tools.reader_layout` (`data/cache/reader-layout.json`).
//!
//! - `Layout::load`: read the file
//! - `Layout::field`: a field's offset by `Class.Field`
//! - `Layout::follow`: the object at the end of a chain of pointer fields
//! - `Layout::type_info`: a root class's type info RVA by full name
//! - `Layout::name`: an enum value's name (the reader writes names, not numbers)
//! - `offsets!`: a struct of one class's field offsets, resolved once, with the span of bytes
//!   that covers them (to read the object in one `Process::block`)

use std::collections::HashMap;

use serde::Deserialize;

use crate::process::Process;

#[derive(Deserialize)]
pub struct Layout {
    pub game_version: String,
    type_info: HashMap<String, u64>,
    fields: HashMap<String, u64>,
    /// enum → value (as text) → name
    enums: HashMap<String, HashMap<String, String>>,
}

impl Layout {
    pub fn load(path: &str) -> Result<Layout, String> {
        let text = std::fs::read_to_string(path).map_err(|e| format!("{path}: {e}"))?;
        serde_json::from_str(&text).map_err(|e| format!("{path}: {e}"))
    }

    pub fn field(&self, name: &str) -> Result<u64, String> {
        self.fields
            .get(name)
            .copied()
            .ok_or_else(|| format!("layout has no {name}"))
    }

    pub fn follow(&self, process: &Process, from: u64, path: &[&str]) -> Result<u64, String> {
        path.iter().try_fold(from, |object, field| {
            process.ptr(object + self.field(field)?, field)
        })
    }

    pub fn name(&self, enumeration: &str, value: i32) -> Result<String, String> {
        self.enums
            .get(enumeration)
            .and_then(|names| names.get(&value.to_string()))
            .cloned()
            .ok_or_else(|| format!("{enumeration} has no {value}: stale layout?"))
    }

    pub fn type_info(&self, class: &str) -> Result<u64, String> {
        self.type_info
            .get(class)
            .copied()
            .ok_or_else(|| format!("layout has no {class}"))
    }
}

macro_rules! offsets {
    ($name:ident, $class:literal { $($field:ident: $key:literal),* $(,)? }) => {
        pub struct $name {
            $(pub $field: u64,)*
            #[allow(dead_code)]
            pub span: u64,
        }

        impl $name {
            pub fn new(layout: &$crate::layout::Layout) -> Result<Self, String> {
                $(let $field = layout.field(concat!($class, ".", $key))?;)*
                let span = [$($field),*].into_iter().max().unwrap_or(0) + 8;
                Ok(Self { $($field,)* span })
            }
        }
    };
}

pub(crate) use offsets;
