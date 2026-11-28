//! The game process, opened for reading only: no injection, no writes.
//!
//! - `Process::open`: find a process and one of its modules by name
//! - `Process::alive`: whether it's still running
//! - `Process::read`, `read_bytes`, `ptr`, `cstr`: copy values out of its memory
//! - `Process::block`, `Block`: an object's bytes in one read, its fields decoded from them
//!   (ints, doubles, pointers, `Nullable<int>`, `<long>` and `<double>`, `Fixed`, `DateTime`)
//! - `Process::find_words`: every place its heap holds a value (objects of a class, by the
//!   class pointer in their header)

use std::ffi::c_void;
use std::mem::{size_of, MaybeUninit};

use windows_sys::Win32::Foundation::{CloseHandle, HANDLE, INVALID_HANDLE_VALUE};
use windows_sys::Win32::System::Diagnostics::Debug::ReadProcessMemory;
use windows_sys::Win32::System::Diagnostics::ToolHelp::{
    CreateToolhelp32Snapshot, Module32FirstW, Module32NextW, Process32FirstW, Process32NextW,
    MODULEENTRY32W, PROCESSENTRY32W, TH32CS_SNAPMODULE, TH32CS_SNAPMODULE32, TH32CS_SNAPPROCESS,
};
use windows_sys::Win32::System::Memory::{
    VirtualQueryEx, MEMORY_BASIC_INFORMATION, MEM_COMMIT, MEM_PRIVATE, PAGE_READWRITE,
};
use windows_sys::Win32::System::Threading::{
    GetExitCodeProcess, OpenProcess, PROCESS_QUERY_INFORMATION, PROCESS_VM_READ,
};

/// How much of the heap one read takes while searching it.
const SEARCH_CHUNK: usize = 1 << 20;

pub struct Process {
    handle: HANDLE,
    pub pid: u32,
    pub module_base: u64,
}

impl Drop for Process {
    fn drop(&mut self) {
        unsafe { CloseHandle(self.handle) };
    }
}

impl Process {
    /// The first process named `exe`, with the base address of its `module`.
    pub fn open(exe: &str, module: &str) -> Result<Process, String> {
        let pid = find_pid(exe).ok_or_else(|| format!("{exe} isn't running"))?;
        let module_base =
            find_module(pid, module).ok_or_else(|| format!("{module} not loaded in {exe}"))?;
        let handle =
            unsafe { OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, 0, pid) };

        if handle.is_null() {
            return Err(format!("can't open {exe} ({pid}) for reading"));
        }

        Ok(Process {
            handle,
            pid,
            module_base,
        })
    }

    pub fn alive(&self) -> bool {
        let mut code = 0u32;
        let ok = unsafe { GetExitCodeProcess(self.handle, &mut code) };
        ok != 0 && code == STILL_ACTIVE
    }

    /// Every 8-aligned address in the heap (committed, private, read-write memory) that holds
    /// `value`. Read only, like everything here; regions that can't be read are skipped.
    pub fn find_words(&self, value: u64) -> Vec<u64> {
        let mut found = Vec::new();
        let mut buffer = vec![0u8; SEARCH_CHUNK];

        for (base, size) in self.heap_regions() {
            let mut offset = 0u64;

            while offset < size {
                let len = SEARCH_CHUNK.min((size - offset) as usize);
                let chunk = &mut buffer[..len];

                if self.read_bytes(base + offset, chunk).is_ok() {
                    found.extend(
                        chunk
                            .chunks_exact(8)
                            .enumerate()
                            .filter(|(_, word)| u64::from_le_bytes((*word).try_into().unwrap()) == value)
                            .map(|(i, _)| base + offset + 8 * i as u64),
                    );
                }

                offset += len as u64;
            }
        }

        found
    }

    fn heap_regions(&self) -> Vec<(u64, u64)> {
        let mut regions = Vec::new();
        let mut addr = 0u64;

        loop {
            let mut info = MaybeUninit::<MEMORY_BASIC_INFORMATION>::zeroed();
            let size = size_of::<MEMORY_BASIC_INFORMATION>();
            let got = unsafe { VirtualQueryEx(self.handle, addr as *const c_void, info.as_mut_ptr(), size) };

            if got == 0 {
                return regions;
            }

            let info = unsafe { info.assume_init() };
            let (base, length) = (info.BaseAddress as u64, info.RegionSize as u64);

            if info.State == MEM_COMMIT && info.Type == MEM_PRIVATE && info.Protect == PAGE_READWRITE {
                regions.push((base, length));
            }

            match base.checked_add(length) {
                Some(next) if next > addr => addr = next,
                _ => return regions,
            }
        }
    }

    pub fn read_bytes(&self, addr: u64, buf: &mut [u8]) -> Result<(), String> {
        let mut done = 0usize;
        let ok = unsafe {
            ReadProcessMemory(
                self.handle,
                addr as *const c_void,
                buf.as_mut_ptr().cast(),
                buf.len(),
                &mut done,
            )
        };

        if ok == 0 || done != buf.len() {
            return Err(format!("can't read {} bytes at {addr:#x}", buf.len()));
        }

        Ok(())
    }

    /// A plain value (integers, pointers) at `addr`.
    pub fn read<T: Copy>(&self, addr: u64) -> Result<T, String> {
        let mut value = MaybeUninit::<T>::uninit();
        let bytes = unsafe {
            std::slice::from_raw_parts_mut(value.as_mut_ptr().cast::<u8>(), size_of::<T>())
        };
        self.read_bytes(addr, bytes)?;
        Ok(unsafe { value.assume_init() })
    }

    /// The pointer at `addr`, which must not be null.
    pub fn ptr(&self, addr: u64, what: &str) -> Result<u64, String> {
        match self.read::<u64>(addr)? {
            0 => Err(format!("{what} is null")),
            p => Ok(p),
        }
    }

    /// The `len` bytes at `addr`, to decode several fields from one read.
    pub fn block(&self, addr: u64, len: u64) -> Result<Block, String> {
        let mut bytes = vec![0u8; len as usize];
        self.read_bytes(addr, &mut bytes)?;
        Ok(Block { bytes })
    }

    /// A NUL-terminated string of at most 256 bytes.
    pub fn cstr(&self, addr: u64) -> Result<String, String> {
        let mut buf = [0u8; 256];
        self.read_bytes(addr, &mut buf)?;
        let end = buf.iter().position(|&b| b == 0).unwrap_or(buf.len());
        Ok(String::from_utf8_lossy(&buf[..end]).into_owned())
    }
}

/// The exit code of a process still running
const STILL_ACTIVE: u32 = 259;

const FIXED_DECIMALS: f64 = 1e6;
/// `DateTime`: ticks of 100 ns since 0001-01-01 in the low 62 bits (the top two are its kind)
const DATETIME_TICKS: u64 = 0x3FFF_FFFF_FFFF_FFFF;
const TICKS_AT_UNIX_EPOCH: i64 = 621_355_968_000_000_000;
const TICKS_PER_SECOND: i64 = 10_000_000;

/// An object's bytes, read at once; offsets are from the object's start.
pub struct Block {
    bytes: Vec<u8>,
}

impl Block {
    fn at<const N: usize>(&self, offset: u64) -> [u8; N] {
        self.bytes[offset as usize..][..N].try_into().unwrap()
    }

    /// Raw bytes (a `Guid`, say).
    pub fn bytes(&self, offset: u64, len: usize) -> Vec<u8> {
        self.bytes[offset as usize..][..len].to_vec()
    }

    pub fn i32(&self, offset: u64) -> i32 {
        i32::from_le_bytes(self.at(offset))
    }

    pub fn i64(&self, offset: u64) -> i64 {
        i64::from_le_bytes(self.at(offset))
    }

    /// A pointer (0 for null).
    pub fn ptr(&self, offset: u64) -> u64 {
        u64::from_le_bytes(self.at(offset))
    }

    pub fn bool(&self, offset: u64) -> bool {
        self.bytes[offset as usize] != 0
    }

    /// A `Nullable<int>` (or int-sized enum): hasValue, then the value at +4.
    pub fn nullable_i32(&self, offset: u64) -> Option<i32> {
        self.bool(offset).then(|| self.i32(offset + 4))
    }

    /// A `Nullable<bool>`: hasValue, then the value at +1.
    pub fn nullable_bool(&self, offset: u64) -> Option<bool> {
        self.bool(offset).then(|| self.bool(offset + 1))
    }

    pub fn f64(&self, offset: u64) -> f64 {
        f64::from_le_bytes(self.at(offset))
    }

    /// A `Nullable<double>`: hasValue, then the value at +8.
    pub fn nullable_f64(&self, offset: u64) -> Option<f64> {
        self.bool(offset).then(|| self.f64(offset + 8))
    }

    /// A `Nullable<long>`: hasValue, then the value at +8.
    pub fn nullable_i64(&self, offset: u64) -> Option<i64> {
        self.bool(offset).then(|| self.i64(offset + 8))
    }

    /// A `Fixed` (Q32.32), rounded back to the decimals the game's values hold (0.13 is
    /// stored as 0.1299999994).
    pub fn fixed(&self, offset: u64) -> f64 {
        let value = self.i64(offset) as f64 / 4294967296.0;
        (value * FIXED_DECIMALS).round() / FIXED_DECIMALS
    }

    /// A `DateTime`, as Unix seconds (the game keeps its times in UTC).
    pub fn unix_seconds(&self, offset: u64) -> i64 {
        let ticks = (self.ptr(offset) & DATETIME_TICKS) as i64;
        (ticks - TICKS_AT_UNIX_EPOCH) / TICKS_PER_SECOND
    }
}

fn find_pid(exe: &str) -> Option<u32> {
    let snap = unsafe { CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0) };

    if snap == INVALID_HANDLE_VALUE {
        return None;
    }

    let mut entry: PROCESSENTRY32W = unsafe { std::mem::zeroed() };
    entry.dwSize = size_of::<PROCESSENTRY32W>() as u32;
    let mut found = None;
    let mut more = unsafe { Process32FirstW(snap, &mut entry) } != 0;

    while more {
        if wide(&entry.szExeFile).eq_ignore_ascii_case(exe) {
            found = Some(entry.th32ProcessID);
            break;
        }

        more = unsafe { Process32NextW(snap, &mut entry) } != 0;
    }

    unsafe { CloseHandle(snap) };
    found
}

fn find_module(pid: u32, module: &str) -> Option<u64> {
    let snap = unsafe { CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid) };

    if snap == INVALID_HANDLE_VALUE {
        return None;
    }

    let mut entry: MODULEENTRY32W = unsafe { std::mem::zeroed() };
    entry.dwSize = size_of::<MODULEENTRY32W>() as u32;
    let mut found = None;
    let mut more = unsafe { Module32FirstW(snap, &mut entry) } != 0;

    while more {
        if wide(&entry.szModule).eq_ignore_ascii_case(module) {
            found = Some(entry.modBaseAddr as u64);
            break;
        }

        more = unsafe { Module32NextW(snap, &mut entry) } != 0;
    }

    unsafe { CloseHandle(snap) };
    found
}

fn wide(chars: &[u16]) -> String {
    let end = chars.iter().position(|&c| c == 0).unwrap_or(chars.len());
    String::from_utf16_lossy(&chars[..end])
}
