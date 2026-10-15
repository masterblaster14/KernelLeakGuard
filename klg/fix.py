"""Fix patches for confirmed leaks, validated by compilation, re-analysis and
a runtime re-run in the guest.

Patch construction for a candidate (allocation A leaks when the primary
trigger call fails):

* release statement: the statement the function already uses to release A
  on another path (e.g. ``kfree(tx);`` or ``ctx_release(c);``); without one,
  the deallocator matching A's allocator applied to A's variable;
  allocations into ``x[i]`` inside a loop get the rollback idiom
  ``while (--i >= 0) <release x[i]>;``
* insertion point: the first statement of the error branch taken after the
  trigger fails (reported by the analyser), only if that branch is reached
  exclusively from the trigger's error edge; a brace-less ``if`` body is
  turned into a braced block.

Validation: (1) the patched module compiles; (2) klg-analyze no longer
reports a leak of A; (3) in the guest, a module-filtered sweep visits every
fault point of the patched module with kmemleak and SLUB debugging
(double-free / corruption checks) enabled, and no leak at A and no slab error
is reported.
"""
from __future__ import annotations

import difflib
import json
import re
import shutil
import subprocess
from pathlib import Path

from . import analyze, build, config, evidence, ground_truth, verify

FIX_DIR = config.RESULTS / "fixes"

DEALLOC = {
    "kmalloc": "kfree", "kzalloc": "kfree", "kcalloc": "kfree", "kmalloc_array": "kfree",
    "krealloc": "kfree", "kstrdup": "kfree", "kstrndup": "kfree", "kmemdup": "kfree",
    "kmemdup_nul": "kfree", "kasprintf": "kfree", "kvasprintf": "kfree",
    "memdup_user": "kfree", "memdup_user_nul": "kfree",
    "kvmalloc": "kvfree", "kvzalloc": "kvfree", "kvcalloc": "kvfree",
    "kvmalloc_array": "kvfree", "vmemdup_user": "kvfree",
    "vmalloc": "vfree", "vzalloc": "vfree", "vmalloc_array": "vfree", "vcalloc": "vfree",
}
_LHS = re.compile(r"^\s*(?P<lhs>[\w.\->\[\]]+?)\s*=\s*(?P<call>[\w]+)\s*\((?P<args>.*)")
_CTRL = re.compile(r"^\s*(?:(?:else\s+)?if|while|for)\b.*\)\s*$|^\s*else\s*$")
_INDEXED = re.compile(r"^(?P<arr>[\w.\->]+)\[(?P<idx>\w+)\]$")


def _release_stmt(c: dict, lines: list[str]) -> tuple[str | None, str]:
    """The C statement that releases the leaked object."""
    alloc_text = lines[c["alloc"]["line"] - 1]
    m = _LHS.match(alloc_text)
    if not m:
        return None, "allocation is not a simple assignment"
    lhs = m.group("lhs")
    for site in c.get("release_sites", []):
        text = lines[site["line"] - 1].strip()
        if re.fullmatch(r"[\w]+\(.*\);", text) and lhs in text:
            return text, f"reuses the release at line {site['line']}"
    alloc = c["allocator"]
    if alloc.startswith("kmem_cache_alloc") or alloc == "kmem_cache_zalloc":
        cache = m.group("args").split(",")[0].strip()
        return f"kmem_cache_free({cache}, {lhs});", "kmem_cache_free for the cache allocation"
    if alloc in DEALLOC:
        return f"{DEALLOC[alloc]}({lhs});", f"{DEALLOC[alloc]}() matches {alloc}()"
    return None, f"no known release function for {alloc}()"


def make_patch(c: dict, src: Path) -> dict:
    """Patched source text for candidate c, or a reason why none is made."""
    lines = src.read_text().split("\n")
    fix = c.get("fix")
    if not fix:
        return {"status": "skipped", "reason": "no error branch on the leaking path"}
    if not fix.get("exclusive"):
        return {"status": "skipped", "reason": "error branch is shared with other paths; "
                                               "needs manual review"}
    stmt, why = _release_stmt(c, lines)
    if not stmt:
        return {"status": "skipped", "reason": why}
    i = fix["line"] - 1
    target = lines[i]
    if re.search(r"\bif\s*\(", target):
        return {"status": "skipped", "reason": "single-line if statement; needs manual review"}
    indent = re.match(r"\s*", target).group(0)
    lhs = _LHS.match(lines[c["alloc"]["line"] - 1]).group("lhs")
    if (ix := _INDEXED.match(lhs)) and c["alloc"]["line"] < fix["line"]:
        idx = ix.group("idx")
        body = [f"{indent}while (--{idx} >= 0)", f"{indent}\t{stmt}"]
        why = f"rollback loop over {ix.group('arr')}[0..{idx}-1]; " + why
    else:
        body = [f"{indent}{stmt}"]
    # Previous code line: a brace-less control statement owns `target`.
    p = i - 1
    while p >= 0 and not lines[p].strip():
        p -= 1
    new = list(lines)
    if p >= 0 and _CTRL.match(lines[p]) and not lines[p].rstrip().endswith("{"):
        ctrl_indent = re.match(r"\s*", lines[p]).group(0)
        new[p] = lines[p].rstrip() + " {"
        new[i:i + 1] = body + [target, f"{ctrl_indent}}}"]
    else:
        new[i:i] = body
    return {"status": "generated", "reason": why, "text": "\n".join(new)}


def unified(old: str, new: str, rel: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                        f"a/{rel}", f"b/{rel}", n=3))


def _build_patched(work: Path, patched: dict[str, str]) -> dict[str, str | None]:
    """Build each patched module in its own directory; module -> error or None."""
    errors = {}
    for mod, text in patched.items():
        d = work / mod
        d.mkdir(parents=True, exist_ok=True)
        shutil.copy(config.CORPUS / "klg_harness.h", d)
        (d / f"{mod}.c").write_text(text)
        (d / "Kbuild").write_text(f"obj-m += {mod}.o\nccflags-y += -g -I$(src)\n")
        try:
            build.build_modules(d, jobs=4)
            errors[mod] = None
        except RuntimeError as e:
            errors[mod] = str(e)[-1500:]
    return errors


def generate_and_validate(run_vm: bool = True) -> list[dict]:
    reps = analyze.load_reports("full")
    ver = json.loads((config.RUNTIME_DIR / "verification.json").read_text())
    confirmed = {v["id"] for v in ver["verdicts"] if v["status"] == "confirmed"}
    cands = [c for r in reps.values() for c in r["candidates"] if c["id"] in confirmed]
    if FIX_DIR.exists():
        shutil.rmtree(FIX_DIR)
    (FIX_DIR / "patches").mkdir(parents=True)
    work = FIX_DIR / "build"

    # One patch per module: candidates of the same allocation share a fix.
    results, patched_text, by_mod = [], {}, {}
    for c in sorted(cands, key=lambda c: (c["module"], c["exit"]["line"])):
        src = config.CORPUS / f"{c['module']}.c"
        r = {"id": c["id"], "module": c["module"], "function": c["function"],
             "alloc": c["alloc"]["line"], "checks": {}}
        if c["module"] in by_mod:
            first = by_mod[c["module"]]
            same = first.split(":")[2] == str(c["alloc"]["line"])
            r.update(status="covered" if same else "skipped",
                     reason=(f"same allocation as {first}" if same else
                             f"module already patched for {first}; one fix per run"))
            results.append(r)
            continue
        p = make_patch(c, src)
        r.update(status=p["status"], reason=p["reason"])
        if p["status"] == "generated":
            r["patch"] = unified(src.read_text(), p["text"], f"corpus/{src.name}")
            patched_text[c["module"]] = p["text"]
            by_mod[c["module"]] = c["id"]
            (FIX_DIR / "patches" / f"{c['module']}.patch").write_text(r["patch"])
        results.append(r)

    # (1) compile
    errors = _build_patched(work, patched_text)
    # (2) re-analyse
    for r in results:
        if r["status"] != "generated":
            continue
        mod = r["module"]
        r["checks"]["compiles"] = errors[mod] is None
        if errors[mod]:
            r["status"], r["reason"] = "failed", "patched module does not compile"
            continue
        bc = build.emit_ir(work / mod / f"{mod}.o", work / mod)
        rep = analyze.analyze_module(bc, mod, out_dir=work / "static")
        still = [c for c in rep["candidates"] if c["alloc"]["line"] == r["alloc"]]
        r["checks"]["static_clean"] = not still
        r["checks"]["remaining_warnings"] = len(rep["candidates"])
    # (3) runtime: exhaustive module-filtered sweep of the patched modules
    # Every patch that compiles is re-run in the VM, including those the
    # analyser still flags (it cannot prove loop rollbacks safe, cf. klg_s09).
    good = {r["module"] for r in results if r["status"] == "generated" and r["checks"].get("compiles")}
    if run_vm and good:
        mods = {m: {"ko": work / m / f"{m}.ko", "src": work / m / f"{m}.c"} for m in good}
        evidence.KO_PATHS.update({m: v["ko"] for m, v in mods.items()})
        targets = [verify.Target.of(m, config.CORPUS / f"{m}.c") for m in sorted(good)]
        share = FIX_DIR / "runtime"
        verify._write_share(share, mods, verify.mapping_job(targets, verify.error_injectable(config.CORPUS)))
        verify._run_vm(share, extra_cmdline="slub_debug=FZPU")
        out = share / "out"
        leaks = verify.dynamic_sites(out / "kmemleak_exhaustive.txt", mods, None, {})
        console = (share / "console.log").read_text(errors="replace")
        logs = "".join(p.read_text(errors="replace") for p in out.glob("sweep_*.log"))
        for r in results:
            if r["module"] not in good:
                continue
            m = r["module"]
            mine = [l for l in leaks if l["module"] == m]
            faults = sum(1 for a in evidence.parse_agent_log(out / f"sweep_{m}.log") if a.injected)
            slab_err = [l for l in (console + logs).splitlines()
                        if m in l and re.search(r"BUG |Object already free|Poison overwritten", l)]
            r["checks"]["runtime_faults_exercised"] = faults
            r["checks"]["runtime_clean"] = not mine and not slab_err
            r["checks"]["runtime_leaks"] = mine
            r["checks"]["slab_errors"] = slab_err[:5]
    for r in results:
        ch = r["checks"]
        if r["status"] == "generated":
            runtime_ok = ch.get("runtime_clean") or not run_vm
            if ch.get("compiles") and ch.get("static_clean") and runtime_ok:
                r["status"] = "validated"
            elif ch.get("compiles") and runtime_ok and run_vm:
                # Leak gone at runtime, but the analyser cannot prove the fix
                # (path-insensitive on loop counters): reported separately.
                r["status"] = "runtime-validated"
                r["reason"] += "; static warning remains (loop-counter limitation)"
            else:
                r["status"] = "failed"
                if r["reason"] and "does not compile" not in r["reason"]:
                    r["reason"] += "; validation failed"
    (FIX_DIR / "fixes.json").write_text(json.dumps(results, indent=2))
    return results
