"""
game_emulator.py - GameAssembly.dll's own methods run in Unicorn (an x86-64 emulator), on objects
built by field name from the dump's layouts: the game's code as a black box to test models
against (tests/test_game_code.py). Nothing of the game runs but the methods called and what they
call. libil2cpp's runtime is stood in for by a few hooks (metadata, class init and static
constructors, object and array allocation, array initialisers), found by where known methods
call them, so a new game version needs no new addresses; anything else of the runtime that the
code reaches stops the call with `Unhandled`, naming where.

- `Game`: where the game's files are (from the environment)
- `Unhandled`, `Nullable`: what a call can raise; a value for a `Nullable<T>` field
- `Runtime`, `find_runtime`: libil2cpp's entry points, from call sites
- `Emulator`: the loaded image and its heap; `new`, `set`, `set_static`, `read`, `call`,
  `replace` (a method answered by Python), `after_call` (where to stop a call)
- `contains_enum`: LINQ's generic `Contains`, answered in Python
- `to_signed`: a returned register as the int64 it holds
"""

import json
import os
import struct
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import capstone
import pefile
from unicorn import UC_ARCH_X86, UC_HOOK_CODE, UC_HOOK_MEM_UNMAPPED, UC_MODE_64, Uc, UcError
from unicorn.x86_const import (
    UC_X86_REG_R8,
    UC_X86_REG_R9,
    UC_X86_REG_RAX,
    UC_X86_REG_RCX,
    UC_X86_REG_RDX,
    UC_X86_REG_RIP,
    UC_X86_REG_RSP,
)

from tools import dump_types
from tools.dump_types import TypeDef

MASK = (1 << 64) - 1
ARGUMENTS = (UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8, UC_X86_REG_R9)

# Il2CppClass / Il2CppArray / Il2CppObject offsets (metadata v39, x64)
STATIC_FIELDS = 0xB8
CCTOR_FINISHED = 0xE4
VTABLE = 0x138  # {methodPtr, MethodInfo*} per slot
ARRAY_LENGTH = 0x18
ARRAY_DATA = 0x20
OBJECT_HEADER = 0x10

METHOD_SPAN = 0x6000  # the most of a method that's disassembled to find its calls

ELEMENT_SIZES = {"byte": 1, "sbyte": 1, "bool": 1, "char": 2, "short": 2, "ushort": 2}
ELEMENT_SIZES |= {"int": 4, "uint": 4, "float": 4}

STACK, STACK_SIZE = 0x7000_0000, 0x40_0000
RETURN = 0x6000_0000  # calls return here, which ends them
HEAP, HEAP_SIZE = 0x2_0000_0000, 0x1000_0000
BUDGET = 20_000_000  # instructions per call


@dataclass(frozen=True)
class Game:
    """The game's files the emulator needs, from `just test-game`'s environment."""

    game_assembly: Path
    metadata: Path
    dump: Path  # data/dump/<version>: dump.cs, script.json

    @staticmethod
    def from_environment() -> "Game | None":
        paths = [os.environ.get(name) for name in ("GAME_ASSEMBLY", "GAME_METADATA", "GAME_DUMP")]
        if not all(paths) or not all(Path(p).exists() for p in paths):
            return None

        return Game(*(Path(p) for p in paths))


class Unhandled(Exception):
    """The code reached something the emulator doesn't stand in for."""


@dataclass(frozen=True)
class Nullable:
    """A `Nullable<T>` field's value (one left out of `new` has none)."""

    value: object


@dataclass(frozen=True)
class Runtime:
    """libil2cpp's entry points that generated code calls, as RVAs."""

    init_metadata: int  # il2cpp_codegen_initialize_runtime_metadata(slot)
    class_init: int  # Runtime::ClassInit(klass): runs the static constructor
    object_new: int  # Object::New(klass)
    array_new: int  # Array::NewSpecific(klass, length)
    throw_null: int  # raises NullReferenceException

    @property
    def end(self) -> int:
        """Past the highest entry point: calls below it from generated code are into libil2cpp
        (a guard for clearer errors; the C runtime, above it, runs as it is)."""
        return (
            max(
                self.init_metadata,
                self.class_init,
                self.object_new,
                self.array_new,
                self.throw_null,
            )
            | 0xFFFF
        ) + 1


@dataclass
class FakeClass:
    address: int
    type: TypeDef
    statics: int  # the static fields' block


class Emulator:
    def __init__(self, game: Game):
        script = json.loads((game.dump / "script.json").read_text())
        self.types = dump_types.load(game.dump / "dump.cs")
        self.global_metadata = game.metadata.read_bytes()

        self.methods: dict[str, list[int]] = {}

        for method in script["ScriptMethod"]:
            self.methods.setdefault(method["Name"], []).append(method["Address"])

        self.metadata = {m["Address"]: m["Name"] for m in script["ScriptMetadata"]}
        self.metadata |= {m["Address"]: m["Name"] for m in script["ScriptMetadataMethod"]}
        self.strings = {s["Address"]: s["Value"] for s in script["ScriptString"]}

        self.uc = Uc(UC_ARCH_X86, UC_MODE_64)
        self.base = self.load_image(game.game_assembly)
        self.disassembler = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.method_starts = sorted({rva for rvas in self.methods.values() for rva in rvas})
        self.runtime = find_runtime(self)
        self.uc.mem_map(STACK, STACK_SIZE)
        self.uc.mem_map(RETURN, 0x1000)
        self.uc.mem_map(HEAP, HEAP_SIZE)
        self.heap_top = HEAP

        self.classes: dict[str, FakeClass] = {}
        self.class_at: dict[int, FakeClass] = {}
        self.field_handles: dict[int, str] = {}
        self.short_names: dict[str, TypeDef] = {}
        self.chains: dict[str, list[TypeDef]] = {}
        self.failure: Exception | None = None

        end = self.base + self.runtime.end
        self.uc.hook_add(UC_HOOK_CODE, self.on_runtime, begin=self.base, end=end)
        self.uc.hook_add(UC_HOOK_MEM_UNMAPPED, self.on_unmapped)

        for rva in self.methods["System.Runtime.CompilerServices.RuntimeHelpers$$InitializeArray"]:
            self.hook(rva, self.initialize_array)

        self.replace("System.Linq.Enumerable$$Contains<Int32Enum>", contains_enum)

    def load_image(self, game_assembly: Path) -> int:
        pe = pefile.PE(str(game_assembly), fast_load=True)
        base = pe.OPTIONAL_HEADER.ImageBase
        self.uc.mem_map(base, (pe.OPTIONAL_HEADER.SizeOfImage + 0xFFF) & ~0xFFF)

        for section in pe.sections:
            self.uc.mem_write(base + section.VirtualAddress, section.get_data())

        return base

    # --- objects ----------------------------------------------------------------------------

    def new(self, type_name: str, **fields) -> int:
        """A new object of the type (zeroed, no constructor run), its fields set by name: an int
        is written as the field's raw value, a bool as a byte, a `Nullable` with its flag."""
        fake = self.klass(type_name)
        address = self.alloc(OBJECT_HEADER + self.instance_size(fake.type))
        self.write_u64(address, fake.address)
        self.set(address, **fields)
        return address

    def set(self, address: int, **fields) -> None:
        fake = self.class_at[self.read_u64(address)]

        for name, value in fields.items():
            member = self.field(fake.type, name)
            self.write_value(address + member.offset, member.type, value)

    def set_static(self, type_name: str, **fields) -> None:
        """Set static fields, after the static constructor has run (as it would on first use)."""
        fake = self.klass(type_name)
        self.initialize(fake)

        for name, value in fields.items():
            member = self.field(fake.type, name)
            self.write_value(fake.statics + member.offset, member.type, value)

    def read(self, address: int, *path: str) -> int:
        """The raw 8 bytes at a path of fields from an object (each but the last a reference)."""
        for name in path[:-1]:
            address = self.read_u64(address + self.field_of(address, name).offset)

        return self.read_u64(address + self.field_of(address, path[-1]).offset)

    def read_byte(self, address: int, name: str) -> int:
        return self.uc.mem_read(address + self.field_of(address, name).offset, 1)[0]

    def field_of(self, address: int, name: str) -> dump_types.Field:
        return self.field(self.class_at[self.read_u64(address)].type, name)

    # --- calls ------------------------------------------------------------------------------

    def call(self, method: str | int, *arguments: int, until: int | None = None) -> int:
        """Call a method by script.json name (`Namespace.Class$$Method`; the first overload) or
        RVA, with integer arguments (a trailing null MethodInfo* is added); returns rax. With
        `until` (an RVA inside it), stop there instead: what's after isn't under test."""
        rva = self.methods[method][0] if isinstance(method, str) else method
        values = [*arguments, 0]
        stack = STACK + STACK_SIZE - 0x2000

        for register, value in zip(ARGUMENTS, values, strict=False):
            self.uc.reg_write(register, value & MASK)

        for i, value in enumerate(values[len(ARGUMENTS) :]):
            self.write_u64(stack + 0x28 + 8 * i, value)

        self.write_u64(stack, RETURN)
        self.uc.reg_write(UC_X86_REG_RSP, stack)

        self.failure = None
        stop = None

        if until is not None:
            at = self.base + until
            stop = self.uc.hook_add(UC_HOOK_CODE, lambda *_: self.uc.emu_stop(), begin=at, end=at)

        try:
            self.uc.emu_start(self.base + rva, RETURN, count=BUDGET)
        except UcError as error:
            raise self.failure or Unhandled(f"{error} at {self.rip():#x}") from None
        finally:
            if stop is not None:
                self.uc.hook_del(stop)

        if self.failure:
            raise self.failure

        return self.uc.reg_read(UC_X86_REG_RAX)

    def replace(self, method: str | int, answer: Callable[["Emulator", list[int]], int]) -> None:
        """Answer a method (every overload of a name, or one RVA) from Python:
        `answer(emulator, [rcx, rdx, r8, r9])` returns rax. For what the emulator can't run
        around the code under test (pools, generic code), never that code itself."""
        for rva in self.methods[method] if isinstance(method, str) else [method]:
            self.hook(rva, lambda: self.return_from_helper(answer(self, self.arguments())))

    def static_array(self, type_name: str, name: str, element: str = "<I") -> list[int]:
        """A static array field's elements, once the class's static constructor has run."""
        fake = self.klass(type_name)
        self.initialize(fake)
        array = self.read_u64(fake.statics + self.field(fake.type, name).offset)
        length = self.read_u64(array + ARRAY_LENGTH)
        size = struct.calcsize(element)
        data = self.uc.mem_read(array + ARRAY_DATA, size * length)
        return [value for (value,) in struct.iter_unpack(element, data)]

    def hook(self, rva: int, action: Callable[[], None]) -> None:
        address = self.base + rva
        self.uc.hook_add(
            UC_HOOK_CODE, lambda uc, at, size, data: action(), begin=address, end=address
        )

    def arguments(self) -> list[int]:
        return [self.uc.reg_read(register) for register in ARGUMENTS]

    def return_from_helper(self, value: int = 0) -> None:
        stack = self.uc.reg_read(UC_X86_REG_RSP)
        self.uc.reg_write(UC_X86_REG_RAX, value & MASK)
        self.uc.reg_write(UC_X86_REG_RIP, self.read_u64(stack))
        self.uc.reg_write(UC_X86_REG_RSP, stack + 8)

    # --- libil2cpp's stand-ins --------------------------------------------------------------

    def calls(self, rva: int) -> list[tuple[int, int]]:
        """A method's direct calls: (the RVA after the call, the callee's RVA)."""
        later = [start for start in self.method_starts if start > rva]
        span = min(later[0] - rva if later else METHOD_SPAN, METHOD_SPAN)
        code = self.uc.mem_read(self.base + rva, span)
        found = []

        for instruction in self.disassembler.disasm(bytes(code), rva):
            if instruction.mnemonic == "int3":
                break

            if instruction.mnemonic == "call" and instruction.op_str.startswith("0x"):
                found.append((instruction.address + instruction.size, int(instruction.op_str, 16)))

        return found

    def after_call(self, method: str, callee: str) -> int:
        """The RVA just after the method's first call to the callee: where `call(until=…)` stops
        once the part under test is done."""
        callees = set(self.methods[callee])
        return next(
            after for after, target in self.calls(self.methods[method][0]) if target in callees
        )

    def on_runtime(self, uc, address, size, data) -> None:
        runtime = self.runtime

        match address - self.base:
            case rva if rva == runtime.init_metadata:
                slot = uc.reg_read(UC_X86_REG_RCX)
                self.write_u64(slot, self.resolve_metadata(slot - self.base))
                self.return_from_helper()
            case rva if rva == runtime.class_init:
                self.run_static_constructor(self.class_at[uc.reg_read(UC_X86_REG_RCX)])
            case rva if rva == runtime.object_new:
                fake = self.class_at[uc.reg_read(UC_X86_REG_RCX)]
                self.return_from_helper(self.new(fake.type.full_name))
            case rva if rva == runtime.array_new:
                fake = self.class_at[uc.reg_read(UC_X86_REG_RCX)]
                length = uc.reg_read(UC_X86_REG_RDX) & 0xFFFFFFFF
                self.return_from_helper(self.new_array(fake, length))
            case rva if rva == runtime.throw_null:
                self.fail(Unhandled(f"NullReferenceException in {self.caller()}"))
            case rva if self.just_called():
                self.fail(Unhandled(f"libil2cpp {rva:#x}, called from {self.caller()}"))

    def on_unmapped(self, uc, access, address, size, value, data) -> bool:
        self.failure = Unhandled(f"unmapped memory {address:#x} at {self.rip():#x}")
        return False

    def resolve_metadata(self, rva: int) -> int:
        if rva in self.strings:
            return self.new_string(self.strings[rva])

        name = self.metadata.get(rva)
        if name is None:
            raise Unhandled(f"metadata slot {rva:#x}")

        if name.endswith("_TypeInfo"):
            return self.klass(name.removesuffix("_TypeInfo")).address

        handle = self.alloc(0x100)  # a MethodInfo or a field: blank unless code reads them

        if name.startswith("Field$<PrivateImplementationDetails>."):
            self.field_handles[handle] = name.split(".", 1)[1]

        return handle

    def run_static_constructor(self, fake: FakeClass) -> None:
        """Where `ClassInit` was called: mark the class initialised and jump into its static
        constructor, which returns to the caller."""
        self.uc.mem_write(fake.address + CCTOR_FINISHED, struct.pack("<I", 1))

        if constructor := self.static_constructor(fake):
            self.uc.reg_write(UC_X86_REG_RIP, self.base + constructor)
        else:
            self.return_from_helper()

    def initialize(self, fake: FakeClass) -> None:
        """Run the class's static constructor now, if it hasn't run."""
        if struct.unpack("<I", self.uc.mem_read(fake.address + CCTOR_FINISHED, 4))[0]:
            return

        self.uc.mem_write(fake.address + CCTOR_FINISHED, struct.pack("<I", 1))

        if constructor := self.static_constructor(fake):
            self.call(constructor)

    def static_constructor(self, fake: FakeClass) -> int | None:
        return next((m.rva for m in fake.type.methods if m.name == ".cctor"), None)

    def initialize_array(self) -> None:
        """`RuntimeHelpers.InitializeArray(array, field)`: the field's data from global-metadata."""
        array, handle = self.arguments()[:2]
        offset = self.type("<PrivateImplementationDetails>").data[self.field_handles[handle]]
        size = self.element_size(self.class_at[self.read_u64(array)])
        length = self.read_u64(array + ARRAY_LENGTH)
        self.uc.mem_write(array + ARRAY_DATA, self.global_metadata[offset : offset + size * length])
        self.return_from_helper()

    def fail(self, error: Exception) -> None:
        self.failure = error
        self.uc.emu_stop()

    def just_called(self) -> bool:
        """At libil2cpp's first instruction, called from generated code."""
        return_rva = self.read_u64(self.uc.reg_read(UC_X86_REG_RSP)) - self.base
        return self.runtime.end <= return_rva < self.method_starts[-1] + METHOD_SPAN

    def caller(self) -> str:
        return f"{self.read_u64(self.uc.reg_read(UC_X86_REG_RSP)) - self.base:#x}"

    def rip(self) -> int:
        return self.uc.reg_read(UC_X86_REG_RIP) - self.base

    # --- classes ----------------------------------------------------------------------------

    def klass(self, type_name: str) -> FakeClass:
        """The type's class: a static block, and a vtable from the dump's slots."""
        type_def = self.type(type_name)
        if type_def.full_name in self.classes:
            return self.classes[type_def.full_name]

        fake = FakeClass(self.alloc(0x1000), type_def, self.alloc(0x1000))
        self.classes[type_def.full_name] = self.class_at[fake.address] = fake
        self.write_u64(fake.address + STATIC_FIELDS, fake.statics)
        finished = 0 if self.static_constructor(fake) else 1
        self.uc.mem_write(fake.address + CCTOR_FINISHED, struct.pack("<I", finished))

        for each in self.chain(type_def):
            for method in each.methods:
                if method.slot is not None:
                    self.write_u64(fake.address + VTABLE + 16 * method.slot, self.base + method.rva)

        return fake

    def type(self, name: str) -> TypeDef:
        """A type by full name, or by a name it ends with (preferring the battle code's, under
        SharedModel). Arrays and generic instances aren't in the dump: they get an empty type."""
        if name in self.types:
            return self.types[name]

        if name in self.short_names:
            return self.short_names[name]

        self.short_names[name] = self.find_type(name)
        return self.short_names[name]

    def find_type(self, name: str) -> TypeDef:
        matches = [found for full, found in self.types.items() if full.endswith("." + name)]
        if len(matches) > 1:
            matches = [m for m in matches if m.namespace.startswith("SharedModel")] or matches

        if len(matches) > 1:
            raise KeyError(f"type {name}: {len(matches)} matches")

        if matches:
            return matches[0]

        self.types[name] = TypeDef("", name, "class", None, -1)
        return self.types[name]

    def chain(self, type_def: TypeDef) -> list[TypeDef]:
        """The type and its bases, root first."""
        if type_def.full_name in self.chains:
            return self.chains[type_def.full_name]

        types = [type_def]
        while base := self.base_of(types[-1]):
            types.append(base)

        self.chains[type_def.full_name] = types[::-1]
        return self.chains[type_def.full_name]

    def base_of(self, type_def: TypeDef) -> TypeDef | None:
        if not type_def.base or is_interface_name(type_def.base):
            return None

        name = type_def.base.split("<")[0]
        if f"{type_def.namespace}.{name}" in self.types:
            return self.types[f"{type_def.namespace}.{name}"]

        matches = [x for full, x in self.types.items() if full.endswith("." + name)]
        return matches[0] if len(matches) == 1 else None

    def field(self, type_def: TypeDef, name: str) -> dump_types.Field:
        """A field by name, or the backing field of the property of that name."""
        for each in reversed(self.chain(type_def)):
            for candidate in (name, f"<{name}>k__BackingField"):
                if candidate in each.fields:
                    return each.fields[candidate]

        raise KeyError(f"{type_def.full_name}.{name}")

    def instance_size(self, type_def: TypeDef) -> int:
        offsets = [
            f.offset for x in self.chain(type_def) for f in x.fields.values() if not f.static
        ]
        return max(offsets, default=0) + 0x20

    def element_size(self, fake: FakeClass) -> int:
        return ELEMENT_SIZES.get(fake.type.name.removesuffix("[]").split(".")[-1], 8)

    # --- memory -----------------------------------------------------------------------------

    def alloc(self, size: int) -> int:
        address = self.heap_top
        self.heap_top += (size + 15) & ~15
        if self.heap_top > HEAP + HEAP_SIZE:
            raise Unhandled("emulator heap exhausted")

        return address

    def new_array(self, fake: FakeClass, length: int) -> int:
        address = self.alloc(ARRAY_DATA + self.element_size(fake) * length)
        self.write_u64(address, fake.address)
        self.write_u64(address + ARRAY_LENGTH, length)
        return address

    def new_string(self, text: str) -> int:
        address = self.alloc(0x14 + 2 * len(text) + 2)
        self.write_u64(address, self.klass("System.String").address)
        self.uc.mem_write(address + 0x10, struct.pack("<I", len(text)))
        self.uc.mem_write(address + 0x14, text.encode("utf-16-le"))
        return address

    def write_value(self, address: int, type_: str, value) -> None:
        match value:
            case bool():
                self.uc.mem_write(address, bytes([value]))
            case int() if field_size(type_) == 4:
                self.uc.mem_write(address, struct.pack("<I", value & 0xFFFFFFFF))
            case int():
                self.write_u64(address, value)
            case Nullable(inner):  # {bool hasValue; T value}, the value at T's alignment
                inner_type = type_.removeprefix("Nullable<").removesuffix(">")
                self.uc.mem_write(address, bytes([1]))
                self.write_value(address + nullable_value_offset(inner_type), inner_type, inner)
            case None:
                pass
            case _:
                raise TypeError(f"{type_}: {value!r}")

    def read_u64(self, address: int) -> int:
        return struct.unpack("<Q", self.uc.mem_read(address, 8))[0]

    def write_u64(self, address: int, value: int) -> None:
        self.uc.mem_write(address, struct.pack("<Q", value & MASK))


FOUR_BYTE = {"int", "uint", "float", "Int32", "UInt32"}


def field_size(type_: str) -> int:
    """8 for references, Fixed and longs; 4 for ints and enums (named `…Id`, `…Type` and the
    like: the dump doesn't say which names are enums, so the battle code's are listed)."""
    if type_ in FOUR_BYTE or type_.endswith(("Id", "TypeId")) or type_ in ENUMS:
        return 4

    return 8


ENUMS = {"HitType", "ElementRelation", "Element", "EffectGroup", "EffectTargetType", "GlanceReason"}


def nullable_value_offset(type_: str) -> int:
    """Where a `Nullable<T>`'s value sits: after its flag, at T's alignment."""
    if type_ in ("bool", "byte", "sbyte"):
        return 1

    return 4 if field_size(type_) == 4 else 8


def is_interface_name(name: str) -> bool:
    return name.startswith("I") and name[1:2].isupper()


def find_runtime(emulator: Emulator) -> Runtime:
    """libil2cpp's entry points, from methods whose calls to them are known: `Fixed * Fixed`
    initialises its metadata, then its class; a getter's only call throws on null; `DecCalc`'s
    static constructor allocates an array right before initialising it; `CreateDamageContext`
    allocates a context right before constructing it."""

    def call_before(method: str, callee: str) -> int:
        callees = set(emulator.methods[callee])
        targets = [target for _, target in emulator.calls(emulator.methods[method][0])]
        return targets[next(i for i, target in enumerate(targets) if target in callees) - 1]

    multiply = dict.fromkeys(
        target
        for _, target in emulator.calls(
            emulator.methods["Plarium.Common.Numerics.Fixed$$op_Multiply"][0]
        )
    )
    init_metadata, class_init = list(multiply)[:2]
    (throw_null,) = {
        target
        for _, target in emulator.calls(
            emulator.methods["SharedModel.Battle.Core.Hero.BattleHero$$get_IsFrozen"][0]
        )
    }
    return Runtime(
        init_metadata=init_metadata,
        class_init=class_init,
        object_new=call_before(
            "SharedModel.Battle.Core.Skill.EffectProcessing.Processors.DamageProcessor$$CreateDamageContext",
            "SharedModel.Battle.Core.Skill.EffectContexts.DamageContext$$.ctor",
        ),
        array_new=call_before(
            "System.Decimal.DecCalc$$.cctor",
            "System.Runtime.CompilerServices.RuntimeHelpers$$InitializeArray",
        ),
        throw_null=throw_null,
    )


def contains_enum(emulator: Emulator, arguments: list[int]) -> int:
    """`Enumerable.Contains<TEnum>(source, value)` over an array: generic code, which needs the
    runtime's generic contexts, so answered here."""
    source, value = arguments[0], arguments[1] & 0xFFFFFFFF
    fake = emulator.class_at[emulator.read_u64(source)]
    if not fake.type.name.endswith("[]"):
        raise Unhandled(f"Enumerable.Contains over a {fake.type.name}")

    length = emulator.read_u64(source + ARRAY_LENGTH)
    data = emulator.uc.mem_read(source + ARRAY_DATA, 4 * length)
    return int(value in (v for (v,) in struct.iter_unpack("<I", data)))


def to_signed(raw: int) -> int:
    return raw - (1 << 64) if raw >> 63 else raw
