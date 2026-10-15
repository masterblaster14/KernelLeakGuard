"""Build the benchmark corpus as kernel modules and extract LLVM IR.

The IR is produced by re-running each module's exact kbuild compile command
(recorded in .<obj>.cmd) with -emit-llvm, so the analysed code sees the same
headers, macros and configuration as the module loaded in the VM.
"""
import re
import subprocess
from pathlib import Path

from . import config


def build_modules(src_dir: Path = config.CORPUS, jobs: int = 8) -> list[Path]:
    """Compile every module in src_dir against the guest kernel."""
    cmd = ["make", "-C", str(config.KSRC), f"O={config.KBUILD}", "LLVM=1",
           f"M={src_dir}", f"-j{jobs}", "modules"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError("module build failed:\n" + res.stdout[-4000:] + res.stderr[-4000:])
    return sorted(src_dir.glob("*.ko"))


_OUT_RE = re.compile(r"\s-o\s+(\S+)\.o(\s)")
_DEP_RE = re.compile(r"\s-Wp,-MMD,\S+")


def _compile_command(obj: Path) -> str:
    cmd_file = obj.parent / f".{obj.name}.cmd"
    text = cmd_file.read_text()
    m = re.search(r"^savedcmd_\S+\s*:=\s*(.*)$", text, re.M)
    if not m:
        raise RuntimeError(f"no compile command in {cmd_file}")
    return m.group(1)


def emit_ir(obj: Path, out_dir: Path = config.IR_DIR, cwd: Path | None = None) -> Path:
    """Re-run the kbuild command for obj (a .o) producing unoptimised bitcode.

    cwd: directory kbuild compiled from (external modules: the module dir;
    in-tree objects: the kernel build directory)."""
    out_dir = out_dir.resolve()          # the compiler runs from another directory
    out_dir.mkdir(parents=True, exist_ok=True)
    bc = out_dir / (obj.stem + ".bc")
    cmd = _compile_command(obj)
    cmd = cmd.split(" ; ")[0]                      # drop chained post-processing
    cmd = _DEP_RE.sub("", cmd)
    if not _OUT_RE.search(cmd):
        raise RuntimeError(f"unexpected compile command for {obj}")
    # -O2 semantics in the front end (macros, inline definitions) but no LLVM
    # optimisation passes: the analyser sees the program structure as written.
    cmd = _OUT_RE.sub(f" -emit-llvm -Xclang -disable-llvm-passes -g -o {bc}\\2", cmd, count=1)
    # Since Linux 6.13 kbuild compiles external modules from inside M=.
    res = subprocess.run(cmd, shell=True, cwd=cwd or obj.parent, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"IR generation failed for {obj}:\n{res.stderr[-3000:]}")
    return bc


def build_guest():
    """klg-agent, the guest initramfs and the klg_modwatch helper module."""
    res = subprocess.run(["bash", str(config.ROOT / "vm" / "build_initramfs.sh")],
                         capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError("initramfs build failed:\n" + res.stdout + res.stderr)
    build_modules(config.ROOT / "runtime" / "modwatch")


def build_all(src_dir: Path = config.CORPUS) -> dict[str, dict]:
    """Build modules and IR; returns {module: {"ko": path, "bc": path, "src": path}}."""
    config.ensure_dirs()
    build_guest()
    kos = build_modules(src_dir)
    out = {}
    for ko in kos:
        name = ko.stem
        obj = ko.with_suffix(".o")
        out[name] = {"ko": ko, "bc": emit_ir(obj), "src": ko.with_suffix(".c")}
    return out
