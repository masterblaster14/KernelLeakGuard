"""Parsing of runtime evidence produced inside the guest.

* klg-agent logs: one block per attempt with the kernel log lines emitted
  while the target path ran (including fault-injection stack traces).
* kmemleak reports: unreferenced objects with their allocation backtraces.
* Stack frames ("func+0x1c/0x60 [module]") are mapped to source lines of the
  module with the kernel's scripts/faddr2line.
"""
import os
import re
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from . import config

FRAME_RE = re.compile(r"([A-Za-z_][\w.]*)\+(0x[0-9a-f]+)/(0x[0-9a-f]+)(?:\s+\[(\w+)\])?")
ATTEMPT_RE = re.compile(r"^@@ATTEMPT n=(-?\d+) ret=(-?\d+) errno=(\d+) injected=(\d)")


@dataclass
class Frame:
    func: str
    offset: int
    size: int
    module: str | None

    @property
    def text(self) -> str:
        return f"{self.func}+{self.offset:#x}/{self.size:#x}"


@dataclass
class Attempt:
    n: int
    ret: int
    errno: int
    injected: bool
    kmsg: list[str] = field(default_factory=list)

    def traced(self) -> bool:
        """False for faults injected silently (allocations with __GFP_NOWARN)."""
        return any("FAULT_INJECTION: forcing a failure" in line for line in self.kmsg)

    def fault_frames(self) -> list[Frame]:
        """Frames of the stack trace printed when the fault was injected."""
        frames, inside = [], False
        for line in self.kmsg:
            if "FAULT_INJECTION: forcing a failure" in line:
                inside, frames = True, []
                continue
            if inside:
                m = FRAME_RE.search(line)
                if m:
                    frames.append(_frame(m))
                elif "</TASK>" in line:
                    inside = False
        return frames


@dataclass
class LeakObject:
    address: str
    size: int
    comm: str
    frames: list[Frame]
    # Return addresses inside the module area that no longer resolve to a
    # symbol: the module was unloaded (e.g. its init failed) before the scan.
    unresolved_module_frames: int = 0
    raw_addresses: list[int] = field(default_factory=list)

    def modules(self) -> set[str]:
        return {f.module for f in self.frames if f.module}

    def resolve(self, symmap: "SymbolMap", candidates: set[str] | None = None) -> bool:
        """Turn raw module addresses into frames using klg_modwatch's symbol
        dumps. Returns True if at least one address was resolved."""
        done = False
        for addr in self.raw_addresses:
            fr = symmap.resolve(addr, candidates)
            if fr:
                self.frames.append(fr)
                done = True
        if done:
            self.unresolved_module_frames = 0
        return done


class SymbolMap:
    """Module layouts and function symbols logged by klg_modwatch."""

    MOD_RE = re.compile(r"KLG-MOD (\w+) text=(?:0x)?([0-9a-f]+)\+([0-9a-f]+) init=(?:0x)?([0-9a-f]+)\+([0-9a-f]+)")
    SYM_RE = re.compile(r"KLG-SYM (\w+) (?:0x)?([0-9a-f]+) (\S+)")

    def __init__(self):
        # (module, text_base, init_base) -> [(start, end)] regions
        self.layouts: dict[tuple[str, int, int], list[tuple[int, int]]] = {}
        self.symbols: dict[str, list[tuple[int, str]]] = {}   # module -> sorted symbols

    @classmethod
    def from_logs(cls, paths) -> "SymbolMap":
        sm = cls()
        syms: dict[str, set[tuple[int, str]]] = {}
        for p in paths:
            try:
                text = Path(p).read_text(errors="replace")
            except OSError:
                continue
            for m in cls.MOD_RE.finditer(text):
                name, tb, ts, ib, isz = m.group(1), *(int(g, 16) for g in m.groups()[1:])
                regions = [(tb, tb + ts)] + ([(ib, ib + isz)] if ib and isz else [])
                sm.layouts[(name, tb, ib)] = regions
            for m in cls.SYM_RE.finditer(text):
                syms.setdefault(m.group(1), set()).add((int(m.group(2), 16), m.group(3)))
        sm.symbols = {k: sorted(v) for k, v in syms.items()}
        return sm

    def resolve(self, addr: int, candidates: set[str] | None = None) -> Frame | None:
        owners = {name for (name, _, _), regs in self.layouts.items()
                  if any(a <= addr < b for a, b in regs)}
        if candidates is not None:
            owners &= candidates
        if len(owners) != 1:
            return None                        # unknown or ambiguous over time
        name = owners.pop()
        best = None
        for start, sym in self.symbols.get(name, []):
            if start <= addr:
                best = (start, sym)
            else:
                break
        if not best:
            return None
        return Frame(best[1], addr - best[0], 0, name)


MODULES_VADDR = 0xFFFFFFFFA0000000
_RAW_FRAME_RE = re.compile(r"^\s*(?:\[<[0-9a-f]+>\]\s*)?0x([0-9a-f]{16})\s*$", re.M)


def _frame(m: re.Match) -> Frame:
    return Frame(m.group(1), int(m.group(2), 16), int(m.group(3), 16), m.group(4))


def parse_agent_log(path: Path) -> list[Attempt]:
    attempts, cur = [], None
    if not path.exists():
        return attempts
    for line in path.read_text(errors="replace").splitlines():
        m = ATTEMPT_RE.match(line)
        if m:
            cur = Attempt(int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4) == "1")
            attempts.append(cur)
        elif line.startswith("K ") and cur is not None:
            cur.kmsg.append(line[2:])
        elif line.startswith("@@END"):
            cur = None
    return attempts


def parse_kmemleak(text: str) -> list[LeakObject]:
    leaks = []
    blocks = re.split(r"(?m)^unreferenced object ", text)
    for b in blocks[1:]:
        head = re.match(r"(0x[0-9a-f]+) \(size (\d+)\)", b)
        if not head:
            continue
        comm = re.search(r'comm "([^"]*)"', b)
        bt = b.split("backtrace", 1)[1] if "backtrace" in b else ""
        frames = [_frame(m) for m in FRAME_RE.finditer(bt)]
        raw = [int(m.group(1), 16) for m in _RAW_FRAME_RE.finditer(bt)
               if int(m.group(1), 16) >= MODULES_VADDR]
        leaks.append(LeakObject(head.group(1), int(head.group(2)),
                                comm.group(1) if comm else "", frames, len(raw), raw))
    return leaks


@lru_cache(maxsize=None)
def _faddr2line(ko: str, func: str, offset: int, size: int) -> tuple[tuple[str, int], ...]:
    """Source locations (innermost first) for a return address in ko."""
    # No "/size": kallsyms sizes include alignment padding and would not match
    # the ELF symbol size, which makes faddr2line skip the address.
    target = f"{func}+{offset:#x}"
    # binutils mode: the script's LLVM=1 mode passes options llvm-addr2line rejects.
    env = {k: v for k, v in os.environ.items() if k != "LLVM"}
    res = subprocess.run([str(config.FADDR2LINE), ko, target], capture_output=True,
                         text=True, env=env)
    locs = []
    for line in res.stdout.splitlines():
        m = re.search(r" at (\S+):(\d+)", line)
        if m:
            locs.append((m.group(1), int(m.group(2))))
    return tuple(locs)


# Where each module's .ko lives (set by the verifier); default: corpus/<m>.ko.
KO_PATHS: dict[str, Path] = {}

Loc = tuple[str, int]          # (source file name, line)


def ko_path(module: str) -> Path:
    return KO_PATHS.get(module, config.CORPUS / f"{module}.ko")


def frame_locs(frame: Frame) -> list[Loc]:
    """Source locations (.c files only, innermost first) of a module frame.

    Frames are return addresses, so the offset is moved back by one byte to
    land inside the call instruction. Header locations (inlined helpers such
    as kmalloc()) are skipped; the enclosing .c location follows them.
    """
    if not frame.module:
        return []
    ko = ko_path(frame.module)
    if not ko.exists():
        return []
    off = frame.offset - 1 if frame.offset > 0 else 0
    return [(Path(f).name, ln) for f, ln in _faddr2line(str(ko), frame.func, off, frame.size)
            if f.endswith(".c")]


def module_frame_info(frames: list[Frame], module: str) -> tuple[list[Loc], list[str]]:
    """Source locations of `module` in a backtrace (innermost first), and the
    module functions whose frames have no source location (merged debug
    locations, e.g. after loop unrolling)."""
    locs: list[Loc] = []
    unresolved: list[str] = []
    for fr in frames:
        if fr.module != module:
            continue
        ls = frame_locs(fr)
        locs += [l for l in ls if l not in locs]
        if not ls and fr.func not in unresolved:
            unresolved.append(fr.func)
    return locs, unresolved


def loc_of(entry: dict) -> Loc:
    """(file name, line) of an analyser location such as candidate["alloc"]."""
    return (Path(entry.get("file", "")).name, entry["line"])


def single_site(alloc_sites: dict, func: str) -> Loc | None:
    """Location of the only allocation site in func, if it has exactly one."""
    sites = alloc_sites.get(func, [])
    return loc_of(sites[0]) if len(sites) == 1 else None
