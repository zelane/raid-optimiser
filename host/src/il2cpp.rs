//! The game's code, through il2cpp's embedding API: GameAssembly.dll loaded into this process
//! and started, then its classes, methods and fields by name. Managed exceptions come back as
//! `Err` with their whole chain (message and stack trace of each inner exception).
//!
//! - `Ptr`: an il2cpp pointer (object, class, method, field)
//! - `Il2cpp`: the started runtime; `start` loads and starts it
//! - its helpers: `class`, `method`, `call`, `new_object`, `string`, `text`, `field`, `get`,
//!   `set_i32`, `set_ref`, `get_static`, `set_static`, `class_of`, `getter`, `type_of`

use std::ffi::{c_char, c_void, CStr, CString};
use std::os::windows::ffi::OsStrExt;
use std::ptr::null_mut;

use windows_sys::Win32::System::LibraryLoader::{
    GetProcAddress, LoadLibraryExW, LOAD_WITH_ALTERED_SEARCH_PATH,
};

pub type Ptr = *mut c_void;

type Invoke = unsafe extern "C" fn(Ptr, Ptr, *mut Ptr, *mut Ptr) -> Ptr;

pub struct Il2cpp {
    images: Vec<Ptr>,
    class_from_name: unsafe extern "C" fn(Ptr, *const c_char, *const c_char) -> Ptr,
    class_get_method: unsafe extern "C" fn(Ptr, *const c_char, i32) -> Ptr,
    class_get_field: unsafe extern "C" fn(Ptr, *const c_char) -> Ptr,
    class_get_type: unsafe extern "C" fn(Ptr) -> Ptr,
    type_get_object: unsafe extern "C" fn(Ptr) -> Ptr,
    static_set: unsafe extern "C" fn(Ptr, Ptr),
    static_get: unsafe extern "C" fn(Ptr, Ptr),
    field_set: unsafe extern "C" fn(Ptr, Ptr, Ptr),
    field_get: unsafe extern "C" fn(Ptr, Ptr, Ptr),
    invoke: Invoke,
    object_new: unsafe extern "C" fn(Ptr) -> Ptr,
    object_get_class: unsafe extern "C" fn(Ptr) -> Ptr,
    object_unbox: unsafe extern "C" fn(Ptr) -> Ptr,
    string_new_len: unsafe extern "C" fn(*const c_char, u32) -> Ptr,
    string_chars: unsafe extern "C" fn(Ptr) -> *const u16,
    string_length: unsafe extern "C" fn(Ptr) -> i32,
    format_exception: unsafe extern "C" fn(Ptr, *mut c_char, i32),
}

/// Loads GameAssembly.dll (its own folder first for what it links: baselib.dll), registers the
/// internal calls the host answers (`internal_calls`, before anything runs), and starts il2cpp
/// with its metadata from `data_dir` (the game's `Raid_Data/il2cpp_data`).
pub fn start(
    game_assembly: &str,
    data_dir: &str,
    internal_calls: &[(&CStr, Ptr)],
) -> Result<Il2cpp, String> {
    unsafe {
        let path: Vec<u16> = std::ffi::OsStr::new(game_assembly)
            .encode_wide()
            .chain(Some(0))
            .collect();
        let module = LoadLibraryExW(path.as_ptr(), null_mut(), LOAD_WITH_ALTERED_SEARCH_PATH);
        if module.is_null() {
            return Err(format!("can't load {game_assembly}"));
        }

        let set_data_dir: unsafe extern "C" fn(*const c_char) = sym(module, "il2cpp_set_data_dir")?;
        let add_internal_call: unsafe extern "C" fn(*const c_char, Ptr) =
            sym(module, "il2cpp_add_internal_call")?;
        let init: unsafe extern "C" fn(*const c_char) -> i32 = sym(module, "il2cpp_init")?;
        let domain_get: unsafe extern "C" fn() -> Ptr = sym(module, "il2cpp_domain_get")?;
        let thread_attach: unsafe extern "C" fn(Ptr) -> Ptr = sym(module, "il2cpp_thread_attach")?;
        let assemblies: unsafe extern "C" fn(Ptr, *mut usize) -> *const Ptr =
            sym(module, "il2cpp_domain_get_assemblies")?;
        let image_of: unsafe extern "C" fn(Ptr) -> Ptr = sym(module, "il2cpp_assembly_get_image")?;

        let data_dir = CString::new(data_dir).map_err(|e| e.to_string())?;
        set_data_dir(data_dir.as_ptr());

        for (name, function) in internal_calls {
            add_internal_call(name.as_ptr(), *function);
        }

        if init(c"IL2CPP Root Domain".as_ptr()) == 0 {
            return Err("il2cpp_init failed".into());
        }

        let domain = domain_get();
        thread_attach(domain);
        let mut count = 0usize;
        let list = assemblies(domain, &mut count);
        let images = (0..count).map(|i| image_of(*list.add(i))).collect();

        Ok(Il2cpp {
            images,
            class_from_name: sym(module, "il2cpp_class_from_name")?,
            class_get_method: sym(module, "il2cpp_class_get_method_from_name")?,
            class_get_field: sym(module, "il2cpp_class_get_field_from_name")?,
            class_get_type: sym(module, "il2cpp_class_get_type")?,
            type_get_object: sym(module, "il2cpp_type_get_object")?,
            static_set: sym(module, "il2cpp_field_static_set_value")?,
            static_get: sym(module, "il2cpp_field_static_get_value")?,
            field_set: sym(module, "il2cpp_field_set_value")?,
            field_get: sym(module, "il2cpp_field_get_value")?,
            invoke: sym(module, "il2cpp_runtime_invoke")?,
            object_new: sym(module, "il2cpp_object_new")?,
            object_get_class: sym(module, "il2cpp_object_get_class")?,
            object_unbox: sym(module, "il2cpp_object_unbox")?,
            string_new_len: sym(module, "il2cpp_string_new_len")?,
            string_chars: sym(module, "il2cpp_string_chars")?,
            string_length: sym(module, "il2cpp_string_length")?,
            format_exception: sym(module, "il2cpp_format_exception")?,
        })
    }
}

unsafe fn sym<T: Copy>(module: Ptr, name: &str) -> Result<T, String> {
    let c = CString::new(name).map_err(|e| e.to_string())?;
    let found = GetProcAddress(module, c.as_ptr() as *const u8)
        .ok_or_else(|| format!("GameAssembly.dll has no {name}"))?;
    Ok(std::mem::transmute_copy(&found))
}

impl Il2cpp {
    pub fn class(&self, namespace: &str, name: &str) -> Result<Ptr, String> {
        let (ns, n) = (cstring(namespace)?, cstring(name)?);

        self.images
            .iter()
            .map(|&image| unsafe { (self.class_from_name)(image, ns.as_ptr(), n.as_ptr()) })
            .find(|class| !class.is_null())
            .ok_or_else(|| format!("no class {namespace}.{name}"))
    }

    pub fn method(&self, class: Ptr, name: &str, arguments: i32) -> Result<Ptr, String> {
        let n = cstring(name)?;
        let method = unsafe { (self.class_get_method)(class, n.as_ptr(), arguments) };

        if method.is_null() {
            return Err(format!("no method {name} taking {arguments}"));
        }

        Ok(method)
    }

    /// Calls a method (`this` null for a static one); value-type arguments go by pointer,
    /// objects as themselves. A managed exception is the `Err`.
    pub fn call(&self, method: Ptr, this: Ptr, arguments: &mut [Ptr]) -> Result<Ptr, String> {
        let mut exception: Ptr = null_mut();
        let result = unsafe { (self.invoke)(method, this, arguments.as_mut_ptr(), &mut exception) };

        if exception.is_null() {
            return Ok(result);
        }

        Err(self.exception_chain(exception))
    }

    pub fn new_object(&self, class: Ptr, arguments: &mut [Ptr]) -> Result<Ptr, String> {
        let object = unsafe { (self.object_new)(class) };
        self.call(self.method(class, ".ctor", arguments.len() as i32)?, object, arguments)?;
        Ok(object)
    }

    pub fn string(&self, text: &str) -> Ptr {
        unsafe { (self.string_new_len)(text.as_ptr() as *const c_char, text.len() as u32) }
    }

    pub fn text(&self, string: Ptr) -> String {
        if string.is_null() {
            return String::new();
        }

        unsafe {
            let length = (self.string_length)(string) as usize;
            String::from_utf16_lossy(std::slice::from_raw_parts((self.string_chars)(string), length))
        }
    }

    /// The `System.Type` of a class, for methods that take one.
    pub fn type_of(&self, class: Ptr) -> Ptr {
        unsafe { (self.type_get_object)((self.class_get_type)(class)) }
    }

    pub fn field(&self, object: Ptr, name: &str) -> Result<Ptr, String> {
        let class = unsafe { (self.object_get_class)(object) };
        let n = cstring(name)?;
        let field = unsafe { (self.class_get_field)(class, n.as_ptr()) };

        if field.is_null() {
            return Err(format!("no field {name}"));
        }

        Ok(field)
    }

    /// A field's value: `T` is its own type (a pointer for an object).
    pub fn get<T: Default>(&self, object: Ptr, name: &str) -> Result<T, String> {
        let mut value = T::default();
        let field = self.field(object, name)?;
        unsafe { (self.field_get)(object, field, &mut value as *mut T as Ptr) };
        Ok(value)
    }

    pub fn set_i32(&self, object: Ptr, name: &str, mut value: i32) -> Result<(), String> {
        let field = self.field(object, name)?;
        unsafe { (self.field_set)(object, field, &mut value as *mut i32 as Ptr) };
        Ok(())
    }

    /// An object field set to `value` (il2cpp takes the object itself for reference fields).
    pub fn set_ref(&self, object: Ptr, name: &str, value: Ptr) -> Result<(), String> {
        let field = self.field(object, name)?;
        unsafe { (self.field_set)(object, field, value) };
        Ok(())
    }

    /// A static object field's value.
    pub fn get_static(&self, class: Ptr, name: &str) -> Result<Ptr, String> {
        let n = cstring(name)?;
        let field = unsafe { (self.class_get_field)(class, n.as_ptr()) };

        if field.is_null() {
            return Err(format!("no static field {name}"));
        }

        let mut value: Ptr = null_mut();
        unsafe { (self.static_get)(field, &mut value as *mut Ptr as Ptr) };
        Ok(value)
    }

    pub fn class_of(&self, object: Ptr) -> Ptr {
        unsafe { (self.object_get_class)(object) }
    }

    pub fn set_static(&self, class: Ptr, name: &str, value: Ptr) -> Result<(), String> {
        let n = cstring(name)?;
        let field = unsafe { (self.class_get_field)(class, n.as_ptr()) };

        if field.is_null() {
            return Err(format!("no static field {name}"));
        }

        unsafe { (self.static_set)(field, value) };
        Ok(())
    }

    /// A property getter's value-type result, unboxed.
    pub fn getter<T: Copy>(&self, object: Ptr, getter: &str) -> Result<T, String> {
        let class = unsafe { (self.object_get_class)(object) };
        let boxed = self.call(self.method(class, getter, 0)?, object, &mut [])?;
        Ok(unsafe { *((self.object_unbox)(boxed) as *const T) })
    }

    fn exception_chain(&self, first: Ptr) -> String {
        let Ok(exception) = self.class("System", "Exception") else {
            return "an exception (System.Exception not found to describe it)".into();
        };
        let inner = self.method(exception, "get_InnerException", 0).ok();
        let trace = self.method(exception, "get_StackTrace", 0).ok();
        let mut text = String::new();
        let mut current = first;

        while !current.is_null() {
            let mut buffer = vec![0 as c_char; 16384];
            unsafe {
                (self.format_exception)(current, buffer.as_mut_ptr(), buffer.len() as i32);
                text += &CStr::from_ptr(buffer.as_ptr()).to_string_lossy();
            }
            text.push('\n');

            let mut ignored: Ptr = null_mut();
            if let Some(getter) = trace {
                let stack = unsafe { (self.invoke)(getter, current, null_mut(), &mut ignored) };
                text += &format!("{}\n", self.text(stack));
            }

            current = match inner {
                Some(getter) => unsafe { (self.invoke)(getter, current, null_mut(), &mut ignored) },
                None => null_mut(),
            };
        }

        text
    }
}

fn cstring(text: &str) -> Result<CString, String> {
    CString::new(text).map_err(|e| e.to_string())
}
