//! The Unity engine calls the game's code makes outside a battle, answered by the host (there
//! is no Unity here): the data folder, the version, and freeing what they hand out.
//!
//! - `Answers`: what the host says, set once before il2cpp starts
//! - `internal_calls`: the calls, by the names il2cpp looks them up by

use std::ffi::CStr;
use std::sync::OnceLock;

use crate::il2cpp::Ptr;

/// `persistent_data_path` must be a copy of the game's LocalLow folder (what the game's loaders
/// read there they may also delete: its static-data cache loader clears the cache when a load
/// fails); `version` names the static data's folder in it.
pub struct Answers {
    pub persistent_data_path: String,
    pub version: String,
}

static PERSISTENT_DATA_PATH: OnceLock<Vec<u16>> = OnceLock::new();
static VERSION: OnceLock<Vec<u16>> = OnceLock::new();

/// Unity's newer bindings return a string as a span of UTF-16 the caller frees afterwards.
#[repr(C)]
struct ManagedSpanWrapper {
    begin: *const u16,
    length: i32,
}

pub fn internal_calls(answers: Answers) -> Vec<(&'static CStr, Ptr)> {
    let _ = PERSISTENT_DATA_PATH.set(answers.persistent_data_path.encode_utf16().collect());
    let _ = VERSION.set(answers.version.encode_utf16().collect());

    vec![
        (
            c"UnityEngine.Application::get_persistentDataPath_Injected",
            persistent_data_path as Ptr,
        ),
        (c"UnityEngine.Application::get_version_Injected", version as Ptr),
        (c"UnityEngine.Bindings.BindingsAllocator::Free", free as Ptr),
    ]
}

unsafe extern "C" fn persistent_data_path(out: *mut ManagedSpanWrapper) {
    answer(&PERSISTENT_DATA_PATH, out);
}

unsafe extern "C" fn version(out: *mut ManagedSpanWrapper) {
    answer(&VERSION, out);
}

/// The spans handed out are the host's own statics: nothing to free.
unsafe extern "C" fn free(_buffer: Ptr) {}

unsafe fn answer(text: &OnceLock<Vec<u16>>, out: *mut ManagedSpanWrapper) {
    let text = text.get().map(Vec::as_slice).unwrap_or(&[]);
    (*out).begin = text.as_ptr();
    (*out).length = text.len() as i32;
}
