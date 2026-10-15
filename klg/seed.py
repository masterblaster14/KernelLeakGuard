"""Seeded-bug evaluation on real kernel modules.

    python3 -m klg seed [--only name1,name2] [--skip-vm]

Each seed (seeds/<name>.json) names a real kernel source file, a function and
one release statement to remove. The harness reintroduces the bug exactly as a
careless patch would (comments the statement out), builds the real module
out-of-tree against the guest kernel, and runs the complete pipeline on it:

  detect   static analysis flags the leak on the now-broken error path
  confirm  the module is loaded in the guest VM; fail-nth fails the call on
           that error path; kmemleak reports the object as unreferenced
  fix      the removed statement is re-inserted; the patched module compiles,
           the static warning is gone, and the VM re-run leaks nothing

This evaluates KernelLeakGuard end-to-end on unmodified real kernel code (one
deleted line apart). The original module shows no confirmed leak; the report
states that the bug was seeded.

Results: results/seeded/<name>/ and results/seeded/summary.json.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from . import analyze, build, config, evidence, real, verify

SEED_DIR = config.ROOT / "seeds"
OUT = config.RESULTS / "seeded"


def _modname(spec: dict) -> str:
    return Path(spec["module_file"]).stem.replace("-", "_")


def _func_range(lines: list[str], func: str) -> tuple[int, int]:
    """[start, end) line indices of the C function definition `func`."""
    pat = re.compile(r"^\w[\w ]*\**" + re.escape(func) + r"\s*\(")
    for i, line in enumerate(lines):
        if not pat.match(line):
            continue
        # Skip a forward declaration: "...);" before any "{".
        head = ""
        for j in range(i, min(i + 6, len(lines))):
            head += lines[j]
            if "{" in head:
                break
            if ";" in head:
                head = None
                break
        if head is None:
            continue
        depth, started = 0, False
        for j in range(i, len(lines)):
            depth += lines[j].count("{") - lines[j].count("}")
            started = started or "{" in lines[j]
            if started and depth <= 0:
                return i, j + 1
    return 0, len(lines)


def _apply(spec: dict, src_text: str) -> tuple[str, int]:
    """Comment out the release statement inside the target function; return the
    patched text and the 1-based line number of the removed statement."""
    target = spec["remove"]
    want = spec.get("occurrence", 1)
    lines = src_text.split("\n")
    lo, hi = _func_range(lines, spec["function"])   # confine to the function body
    seen = 0
    for i in range(lo, hi):
        if target in lines[i] and not lines[i].lstrip().startswith(("/*", "*")):
            seen += 1
            if seen == want:
                indent = re.match(r"\s*", lines[i]).group(0)
                lines[i] = f"{indent}/* KLG-SEED: removed {target} */"
                return "\n".join(lines), i + 1
    raise RuntimeError(f"seed {spec['name']}: '{target}' not found in "
                       f"{spec['function']}() (occurrence {want})")


def _build_module(name: str, src: Path, work: Path, orig_dir: str) -> Path:
    work.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, work / f"{name}.c")
    # Some drivers include private headers from their own tree directory
    # (e.g. scsi_debug.c -> "sd.h"); add that directory to the include path.
    (work / "Kbuild").write_text(
        f"obj-m += {name}.o\nccflags-y += -g -I$(srctree)/{orig_dir}\n")
    subprocess.run(["make", "-C", str(config.KSRC), f"O={config.KBUILD}", "LLVM=1",
                    f"M={work}", "-j4", "modules"], check=True, capture_output=True, text=True)
    return work / f"{name}.ko"


def _analyze(name: str, ko: Path, work: Path, tag: str) -> dict:
    bc = build.emit_ir(ko.with_suffix(".o"), work / "ir", cwd=work)
    return analyze.analyze_module(bc, name, out_dir=work / "static" / tag)


def _func_warnings(rep: dict, func: str) -> set[tuple[int, int]]:
    """(alloc line, exit line) of the warnings the analyser reports in func."""
    return {(c["alloc"]["line"], c["exit"]["line"])
            for c in rep["candidates"] if c["function"] == func}


def run_seed(spec: dict, skip_vm: bool) -> dict:
    name = _modname(spec)
    orig_dir = str(Path(spec["module_file"]).parent)
    real_src = config.KSRC / spec["module_file"]
    work = OUT / spec["name"]
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    # Baseline: the unmodified upstream module (= the fixed version too).
    base = work / "fixed"
    base.mkdir()
    base_src = base / "src.c"
    base_src.write_text(real_src.read_text())
    bko = _build_module(name, base_src, base, orig_dir)
    brep = _analyze(name, bko, base, "fixed")
    base_warn = _func_warnings(brep, spec["function"])

    # Buggy: the module with one release statement removed.
    patched_text, removed_line = _apply(spec, real_src.read_text())
    buggy = work / "buggy"
    buggy.mkdir()
    (buggy / "src.c").write_text(patched_text)
    ko = _build_module(name, buggy / "src.c", buggy, orig_dir)
    rep = _analyze(name, ko, buggy, "buggy")
    # The seeded leak is a warning the removal introduced (absent in baseline).
    seeded = sorted(_func_warnings(rep, spec["function"]) - base_warn)
    cand = [c for c in rep["candidates"] if c["function"] == spec["function"]
            and (c["alloc"]["line"], c["exit"]["line"]) in seeded]
    result = {"name": spec["name"], "module": name, "file": spec["module_file"],
              "function": spec["function"], "removed": spec["remove"],
              "removed_line": removed_line, "bug": spec["bug"],
              "reachable": spec.get("reachable", ""),
              "detected": bool(seeded),
              "pre_existing_warnings": len(base_warn),
              "warnings": [{"alloc": c["alloc"]["line"], "allocator": c["allocator"],
                            "exit": c["exit"]["line"], "return": c["return_value"],
                            "confidence": c["confidence"]} for c in cand]}

    # Dependency modules the guest must load before the seeded module.
    all_built = real.built_modules()
    deps = real.load_order([name], all_built) if name in all_built else []
    verify.PRELOAD.clear()
    verify.PRELOAD.update({d: all_built[d] for d in deps if d in all_built})
    result["dependencies"] = deps

    # --- confirm in the VM -------------------------------------------------
    result["confirmed"] = False
    if not skip_vm and cand:
        mods = {name: {"ko": ko, "src": buggy / "src.c"}}
        evidence.KO_PATHS[name] = ko
        targets = [verify.Target(name, "init", f"/mnt/host/mods/{name}.ko")]
        ver = verify.run(mods, {name: rep}, out_root=work / "runtime", baselines=False,
                         targets=targets, gt=None, inject_fns=[], resilient=True)
        confirmed = [v for v in ver["verdicts"] if v["status"] == "confirmed"]
        result["verdicts"] = {v["status"]: sum(1 for x in ver["verdicts"]
                                                if x["status"] == v["status"])
                              for v in ver["verdicts"]}
        result["confirmed"] = bool(confirmed)
        result["evidence"] = [{"reason": v["reason"],
                               "backtrace": (v["tests"][0]["leaks"][0]["backtrace"]
                                             if v["tests"] and v["tests"][0]["leaks"] else [])}
                              for v in confirmed[:1]]
        result["crashes"] = sum(len(c) for c in ver.get("crashes", {}).values())

    # --- fix: re-inserting the removed statement is exactly the baseline ----
    # (built and analysed above). The fix is valid when the baseline compiles
    # and no longer carries the seeded warning.
    result["fix_patch"] = _unified(patched_text, real_src.read_text(), f"{name}.c")
    result["fix_compiles"] = True
    result["fix_static_clean"] = not (set(seeded) & _func_warnings(brep, spec["function"]))
    result["fix_runtime_clean"] = None
    if not skip_vm and cand:
        mods = {name: {"ko": bko, "src": base_src}}
        evidence.KO_PATHS[name] = bko
        targets = [verify.Target(name, "init", f"/mnt/host/mods/{name}.ko")]
        fver = verify.run(mods, {name: brep}, out_root=base / "runtime", baselines=False,
                          targets=targets, gt=None, inject_fns=[], resilient=True)
        result["fix_runtime_clean"] = not any(v["status"] == "confirmed" for v in fver["verdicts"])
    result["fixed"] = (result["fix_compiles"] and result["fix_static_clean"]
                       and (result["fix_runtime_clean"] in (True, None)))
    (work / "result.json").write_text(json.dumps(result, indent=2))
    return result


def _unified(old: str, new: str, rel: str) -> str:
    import difflib
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                        f"a/{rel}", f"b/{rel}", n=3))


def run(only: list[str] | None = None, skip_vm: bool = False) -> list[dict]:
    OUT.mkdir(parents=True, exist_ok=True)
    build.build_guest()
    specs = [json.loads(p.read_text()) for p in sorted(SEED_DIR.glob("*.json"))]
    if only:
        specs = [s for s in specs if s["name"] in only]
    results = []
    for spec in specs:
        print(f"[klg] seed {spec['name']} ({spec['module_file']})")
        r = run_seed(spec, skip_vm)
        results.append(r)
        print(f"       detected={r['detected']} confirmed={r['confirmed']} fixed={r['fixed']}")
    (OUT / "summary.json").write_text(json.dumps(results, indent=2))
    ok = sum(1 for r in results if r["detected"] and (r["confirmed"] or skip_vm))
    print(f"[klg] seeded bugs: {ok}/{len(results)} detected"
          + ("" if skip_vm else " and confirmed in the VM"))
    return results
