//! IL2CPP's runtime class layout (64-bit, metadata v39; `il2cpp.h` in the dump).
//!
//! - `Class`: an `Il2CppClass`: its name, parent and static fields
//! - `Class::from_type_info`: a class through its type info pointer in GameAssembly.dll
//! - `object_class`: the class an object's header points at

use crate::process::Process;

const CLASS_NAME: u64 = 0x10;
const CLASS_NAMESPACE: u64 = 0x18;
const CLASS_PARENT: u64 = 0x58;
const CLASS_STATIC_FIELDS: u64 = 0xB8;

pub struct Class {
    pub addr: u64,
}

impl Class {
    /// The class `full_name` names, through its type info pointer at `rva`, checked by name
    /// (a mismatch means the layout is for another game version).
    pub fn from_type_info(process: &Process, rva: u64, full_name: &str) -> Result<Class, String> {
        let slot = process.module_base + rva;
        let class = Class {
            addr: process.ptr(slot, &format!("{full_name} type info"))?,
        };
        let found = class.full_name(process)?;

        if found != full_name {
            return Err(format!(
                "type info for {full_name} names {found:?}: stale layout?"
            ));
        }

        Ok(class)
    }

    pub fn full_name(&self, process: &Process) -> Result<String, String> {
        let namespace = process.cstr(process.ptr(self.addr + CLASS_NAMESPACE, "namespace")?)?;
        let name = process.cstr(process.ptr(self.addr + CLASS_NAME, "class name")?)?;

        match namespace.is_empty() {
            true => Ok(name),
            false => Ok(format!("{namespace}.{name}")),
        }
    }

    pub fn parent(&self, process: &Process) -> Result<Class, String> {
        Ok(Class {
            addr: process.ptr(self.addr + CLASS_PARENT, "parent class")?,
        })
    }

    /// The static fields block (null until the class is initialised).
    pub fn static_fields(&self, process: &Process) -> Result<u64, String> {
        process.ptr(self.addr + CLASS_STATIC_FIELDS, "static fields")
    }
}

pub fn object_class(process: &Process, object: u64) -> Result<Class, String> {
    Ok(Class {
        addr: process.ptr(object, "object header")?,
    })
}
