"""KernelLeakGuard on real Linux 6.18.55 kernel modules.

    python3 -m klg real [--skip-build] [--skip-vm]

The modules listed in vm/real_modules.fragment initialise without hardware,
so their whole module_init, including every error path in it, can be run in
the guest. For each module: LLVM IR of all its C objects (exact kbuild
flags, linked with llvm-link), static analysis, then in the guest a
module-filtered fault-point sweep of the init path (kmemleak after each
module) and targeted confirmation of every static warning. Guest crashes or
hangs are recorded and the run resumes after the faulting fault point.

Outputs: results/real/static/full/*.json, results/real/runtime/
verification.json, results/real/summary.json. Manual review of the warnings
is kept in results/real/triage.json.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

from . import analyze, build, config, verify

REAL_DIR = config.RESULTS / "real"
FRAGMENT = config.ROOT / "vm" / "real_modules.fragment"

# Kconfig symbol -> module file name (as in modules.order) for the fragment.
MODULE_FILES = {
    "DUMMY": "dummy", "VETH": "veth", "NETDEVSIM": "netdevsim", "BONDING": "bonding",
    "MACVLAN": "macvlan", "IPVLAN": "ipvlan", "NLMON": "nlmon", "TUN": "tun",
    "VXLAN": "vxlan", "GENEVE": "geneve", "NET_TEAM": "team",
    "MAC80211_HWSIM": "mac80211_hwsim", "BLK_DEV_NULL_BLK": "null_blk",
    "BLK_DEV_RAM": "brd", "ZRAM": "zram", "SCSI_DEBUG": "scsi_debug",
    "DM_FLAKEY": "dm-flakey", "DM_DUST": "dm-dust", "DM_DELAY": "dm-delay",
    "MINIX_FS": "minix", "ROMFS_FS": "romfs", "CRAMFS": "cramfs", "SQUASHFS": "squashfs",
    "UDF_FS": "udf", "NILFS2_FS": "nilfs2", "JFS_FS": "jfs", "F2FS_FS": "f2fs",
    "EXFAT_FS": "exfat", "NTFS3_FS": "ntfs3", "HFSPLUS_FS": "hfsplus", "HFS_FS": "hfs",
    "EROFS_FS": "erofs", "QNX4FS_FS": "qnx4", "UFS_FS": "ufs", "OMFS_FS": "omfs",
    "AFFS_FS": "affs", "SND_DUMMY": "snd-dummy", "SND_ALOOP": "snd-aloop",
    "INPUT_UINPUT": "uinput",
}


def modname(file_base: str) -> str:
    """Kernel module name of a module file ("snd-dummy" -> "snd_dummy")."""
    return file_base.replace("-", "_")


def wanted_files() -> list[str]:
    syms = re.findall(r"^CONFIG_(\w+)=m$", FRAGMENT.read_text(), re.M)
    missing = [s for s in syms if s not in MODULE_FILES]
    if missing:
        raise RuntimeError(f"no module file known for {missing}; update MODULE_FILES")
    return [MODULE_FILES[s] for s in syms]


def built_modules() -> dict[str, Path]:
    """Every module of the kernel build: module name -> .ko path."""
    out = {}
    for entry in (config.KBUILD / "modules.order").read_text().split():
        rel = Path(entry).with_suffix("")                 # drivers/net/dummy
        out[modname(rel.name)] = config.KBUILD / rel.with_suffix(".ko")
    return out


def objects_of(ko: Path) -> list[Path]:
    """C objects linked into a module (from kbuild's .mod file)."""
    mod = ko.with_suffix(".mod")
    objs = [config.KBUILD / o for o in mod.read_text().split()]
    return [o for o in objs if _source_of(o).suffix == ".c"]


def _source_of(obj: Path) -> Path:
    cmd = (obj.parent / f".{obj.name}.cmd").read_text()
    m = re.search(r"\s-c -o \S+ (\S+)", cmd)
    return Path(m.group(1)) if m else Path("unknown")


def deps_of(ko: Path) -> list[str]:
    res = subprocess.run(["modinfo", "-F", "depends", str(ko)], capture_output=True, text=True)
    return [modname(d) for d in res.stdout.strip().split(",") if d]


def load_order(names: list[str], all_mods: dict[str, Path]) -> list[str]:
    """Dependencies of `names` (recursively), each after its own dependencies."""
    order: list[str] = []

    def visit(n, stack=()):
        if n in order or n in stack:
            return
        for d in deps_of(all_mods[n]):
            visit(d, stack + (n,))
        order.append(n)

    for n in names:
        for d in deps_of(all_mods[n]):
            visit(d)
    return order


def build_ir(name: str, ko: Path, out_dir: Path) -> tuple[Path | None, dict]:
    """Link the IR of all C objects of a module; returns (bitcode, info)."""
    obj_dir = out_dir / "objs" / name
    bcs, failed = [], []
    for obj in objects_of(ko):
        try:
            bcs.append(build.emit_ir(obj, obj_dir, cwd=config.KBUILD))
        except RuntimeError as e:
            failed.append({"object": str(obj.relative_to(config.KBUILD)), "error": str(e)[-300:]})
    info = {"objects": len(bcs) + len(failed), "ir_failed": failed}
    if not bcs:
        return None, info
    bc = out_dir / f"{name}.bc"
    res = subprocess.run(["llvm-link", "-o", str(bc), *map(str, bcs)], capture_output=True, text=True)
    if res.returncode != 0:
        info["link_error"] = res.stderr[-500:]
        return None, info
    return bc, info


def _source_path(file: str) -> str:
    p = Path(file)
    for cand in (p, config.KBUILD / p, config.KSRC / p):
        if cand.exists():
            return str(cand.resolve())
    return file


def run(skip_build: bool = False, skip_vm: bool = False, only: list[str] | None = None,
        out: Path | None = None) -> dict:
    """only: restrict to these module names (testing); out: results directory."""
    global REAL_DIR
    if out is not None:
        REAL_DIR = out.resolve()
    REAL_DIR.mkdir(parents=True, exist_ok=True)
    all_mods = built_modules()
    files = wanted_files()
    names = [modname(f) for f in files]
    if only:
        names = [n for n in names if n in only]
    absent = [n for n in names if n not in all_mods]
    if absent:
        raise RuntimeError(f"modules not built: {absent}; run ./vm/build_kernel.sh")

    # --- static analysis ------------------------------------------------------
    t0 = time.time()
    reports, ir_info = {}, {}
    static_dir = REAL_DIR / "static"
    if not skip_build:
        build.build_guest()                                 # agent, initramfs, modwatch
    for n in names:
        rep_file = static_dir / "full" / f"{n}.json"
        if skip_build and rep_file.exists():
            reports[n] = json.loads(rep_file.read_text())
            continue
        bc, info = build_ir(n, all_mods[n], REAL_DIR / "ir")
        ir_info[n] = info
        if bc is None:
            print(f"[klg] {n}: no IR ({info})")
            continue
        rep = analyze.analyze_module(bc, n, out_dir=static_dir)
        for c in rep["candidates"]:
            c["source_path"] = _source_path(c["alloc"]["file"])
        rep["ir"] = info
        rep_file.write_text(json.dumps(rep, indent=2))
        reports[n] = rep
        print(f"[klg] {n}: {rep['stats']['functions']} functions, "
              f"{rep['stats']['alloc_sites']} allocation sites, {len(rep['candidates'])} warnings")
    static_s = time.time() - t0

    # --- runtime verification -------------------------------------------------
    deps = load_order(names, all_mods)
    targets_names = [n for n in names if n not in deps and n in reports]
    verify.PRELOAD.clear()
    verify.PRELOAD.update({d: all_mods[d] for d in deps})
    mods = {n: {"ko": all_mods[n], "src": _source_of(objects_of(all_mods[n])[0])}
            for n in targets_names}
    targets = [verify.Target(n, "init", f"/mnt/host/mods/{n}.ko") for n in targets_names]
    ver = {}
    if not skip_vm:
        ver = verify.run(mods, {n: reports[n] for n in targets_names},
                         out_root=REAL_DIR / "runtime", baselines=False, targets=targets,
                         gt=None, inject_fns=[], resilient=True)
    elif (REAL_DIR / "runtime" / "verification.json").exists():
        ver = json.loads((REAL_DIR / "runtime" / "verification.json").read_text())

    # --- summary --------------------------------------------------------------
    counts: dict[str, int] = {}
    for v in ver.get("verdicts", []):
        counts[v["status"]] = counts.get(v["status"], 0) + 1
    crashes = [c for run_ in ver.get("crashes", {}).values() for c in run_]
    # Static statistics cover every analysed module (all 39 even when the
    # runtime part ran on a subset with --only).
    all_reports = {p.stem: json.loads(p.read_text())
                   for p in sorted((static_dir / "full").glob("*.json"))}
    reports = {**all_reports, **reports}
    n_warn = sum(len(r["candidates"]) for r in reports.values())
    summary = {
        "runtime_modules": sorted(targets_names),
        "modules": len(reports),
        "preloaded_dependencies": deps,
        "functions": sum(r["stats"]["functions"] for r in reports.values()),
        "alloc_sites": sum(r["stats"]["alloc_sites"] for r in reports.values()),
        "warnings": n_warn,
        "verdicts": counts,
        "fault_points": ver.get("mapping_executions", 0),
        "confirm_executions": ver.get("confirm_executions", 0),
        "crashes": len(crashes),
        "crash_details": crashes,
        "dynamic_leaks": ver.get("sweep_leaks", []),
        "static_seconds": round(static_s, 1),
        "analysis_ms": round(sum(r["stats"].get("analysis_ms", 0) for r in reports.values()), 1),
        "timing": ver.get("timing", {}),
        "ir": ir_info,
    }
    summary["headline"] = (
        f"{summary['modules']} real modules ({summary['functions']} functions, "
        f"{summary['alloc_sites']} allocation sites): {n_warn} static warnings; runtime: "
        + (", ".join(f"{v} {k}" for k, v in sorted(counts.items())) or "not run")
        + f" ({len(targets_names)} modules run in the VM); "
        f"{summary['fault_points']} fault points of module init exercised; "
        f"{len(summary['dynamic_leaks'])} leak site(s) found by the sweep; "
        f"{summary['crashes']} guest crash(es)/hang(s).")
    (REAL_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    print("[klg] real:", summary["headline"])
    return summary
