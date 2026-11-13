//! Where the walks start: objects held in static fields.
//!
//! - `app_model`: the `AppModel` singleton (`SingleInstance<AppModel>._instance`)
//! - `statics`: a root class's static fields block
//! - `artifact_storage`: the artifact storage the game is configured with, and its class name

use crate::il2cpp::{object_class, Class};
use crate::layout::Layout;
use crate::process::Process;

const APP_MODEL: &str = "Client.Model.AppModel";
const STORAGE_RESOLVER: &str = "SharedModel.Meta.Artifacts.ArtifactStorage.ArtifactStorageResolver";
/// `SingleInstance<T>`'s statics: `Log`, then `_instance` (generic, so not in the layout)
const SINGLETON_INSTANCE: u64 = 0x8;

/// AppModel's class → its parent `SingleInstance<AppModel>`'s statics → `_instance`, checked
/// to be an `AppModel`.
pub fn app_model(process: &Process, layout: &Layout) -> Result<u64, String> {
    let class = Class::from_type_info(process, layout.type_info(APP_MODEL)?, APP_MODEL)?;
    let statics = class.parent(process)?.static_fields(process)?;
    let instance = process.ptr(statics + SINGLETON_INSTANCE, "AppModel (not logged in?)")?;

    if object_class(process, instance)?.addr != class.addr {
        return Err("SingleInstance<AppModel>._instance isn't an AppModel".into());
    }

    Ok(instance)
}

/// The static fields of a class the layout has as a root (by full name).
pub fn statics(process: &Process, layout: &Layout, class: &str) -> Result<u64, String> {
    let rva = layout.type_info(class)?;
    Class::from_type_info(process, rva, class)?.static_fields(process)
}

/// `ArtifactStorageResolver._implementation` and its class's full name.
pub fn artifact_storage(process: &Process, layout: &Layout) -> Result<(u64, String), String> {
    let statics = statics(process, layout, STORAGE_RESOLVER)?;
    let offset = layout.field("ArtifactStorageResolver._implementation")?;
    let storage = process.ptr(statics + offset, "artifact storage")?;
    Ok((storage, object_class(process, storage)?.full_name(process)?))
}
