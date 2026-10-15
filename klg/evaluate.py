"""Evaluation against the corpus ground truth.

Metrics are computed per allocation site: a tool "reports" a site if it
reports at least one leak whose allocation is at that site.

Approaches compared:
  static/<variant>  - klg-analyze alone (full analysis and ablations)
  hybrid            - static candidates confirmed by runtime verification
  exhaustive        - dynamic only: every single fault point + kmemleak
  random            - dynamic only: random fault injection + kmemleak
  cppcheck          - generic C static analyser with a kmalloc/kfree model
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from . import analyze, config, ground_truth


def metrics(reported: set[tuple[str, int]], gt: dict) -> dict:
    leak = {k for k, s in gt.items() if s.label == "LEAK"}
    safe = {k for k, s in gt.items() if s.label == "SAFE"}
    rep = {k for k in reported if k in gt}
    tp, fp = len(rep & leak), len(rep & safe)
    fn, tn = len(leak - rep), len(safe - rep)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": round(prec, 3),
            "recall": round(rec, 3), "f1": round(f1, 3),
            "false_positive_rate": round(fp / (fp + tn), 3) if fp + tn else 0.0,
            "missed": sorted(f"{m}:{l}" for m, l in leak - rep),
            "false_alarms": sorted(f"{m}:{l}" for m, l in rep & safe)}


def static_sites(reports: dict[str, dict]) -> set[tuple[str, int]]:
    return {(c["module"], c["alloc"]["line"]) for r in reports.values() for c in r["candidates"]}


def static_time_ms(reports: dict[str, dict]) -> float:
    return round(sum(r["stats"].get("analysis_ms", 0) for r in reports.values()), 1)


# --- cppcheck baseline ------------------------------------------------------

CPPCHECK_CFG = """<?xml version="1.0"?>
<def format="2">
  <memory>
    <alloc init="false">kmalloc</alloc><alloc init="true">kzalloc</alloc>
    <alloc init="true">kcalloc</alloc><alloc init="false">kmalloc_array</alloc>
    <alloc init="false">kstrdup</alloc><alloc init="false">kmemdup</alloc>
    <alloc init="false">kasprintf</alloc><alloc init="false">kvmalloc</alloc>
    <alloc init="false">vmalloc</alloc><alloc init="true">vzalloc</alloc>
    <dealloc>kfree</dealloc><dealloc>kvfree</dealloc><dealloc>vfree</dealloc>
    <dealloc>kfree_sensitive</dealloc>
  </memory>
</def>
"""


def cppcheck_exe() -> str | None:
    local = config.WORK / "tools" / "cppcheck"       # scripts/install_cppcheck.sh
    return str(local) if local.exists() else shutil.which("cppcheck")


_LHS = re.compile(r"^\s*([\w.\[\]>-]+?)\s*=\s*[\w]+\s*\(")


def cppcheck_sites(src_dir: Path) -> set[tuple[str, int]] | None:
    """Allocation sites cppcheck reports as leaked.

    cppcheck reports "Memory leak: <var>" at the leaking exit; the report is
    mapped to the annotated allocation that assigns <var> (the closest one
    above the exit if several do)."""
    exe = cppcheck_exe()
    if not exe:
        return None
    cfg = config.RESULTS / "kernel.cfg"
    cfg.write_text(CPPCHECK_CFG)
    sites = set()
    for src in sorted(p for p in src_dir.glob("klg_*.c") if ".mod." not in p.name):
        res = subprocess.run([exe, "--enable=warning", f"--library={cfg}", "--quiet",
                              "--template={line}|{id}|{message}", str(src)],
                             capture_output=True, text=True)
        gt_sites = ground_truth.sites_for(src)
        for line in res.stderr.splitlines():
            parts = line.split("|", 2)
            if len(parts) != 3 or not parts[0].isdigit():
                continue
            if parts[1] not in ("memleak", "memleakOnRealloc", "leakReturnValNotUsed"):
                continue
            exit_line = int(parts[0])
            var = parts[2].split(":")[-1].strip()
            named = [s.line for s in gt_sites if s.line <= exit_line
                     and (m := _LHS.match(s.code)) and m.group(1) == var]
            above = named or [s.line for s in gt_sites if s.line <= exit_line]
            if above:
                sites.add((src.stem, max(above)))
    return sites


# --- Evaluation ---------------------------------------------------------------

def evaluate(src_dir: Path = config.CORPUS) -> dict:
    gt = ground_truth.load(src_dir)
    out: dict = {"ground_truth": {
        "modules": len({m for m, _ in gt}),
        "sites": len(gt),
        "leak_sites": sum(1 for s in gt.values() if s.label == "LEAK"),
        "safe_sites": sum(1 for s in gt.values() if s.label == "SAFE"),
    }, "approaches": {}}

    for variant in analyze.VARIANTS:
        reps = analyze.load_reports(variant)
        if not reps:
            continue
        m = metrics(static_sites(reps), gt)
        m["analysis_ms"] = static_time_ms(reps)
        m["warnings"] = sum(len(r["candidates"]) for r in reps.values())
        out["approaches"][f"static/{variant}"] = m

    ver_file = config.RUNTIME_DIR / "verification.json"
    if ver_file.exists():
        ver = json.loads(ver_file.read_text())
        full = analyze.load_reports("full")
        cand = {c["id"]: c for r in full.values() for c in r["candidates"]}
        confirmed = {(cand[v["id"]]["module"], cand[v["id"]]["alloc"]["line"])
                     for v in ver["verdicts"] if v["status"] == "confirmed"}
        hy = metrics(confirmed, gt)
        hy["executions"] = ver["hybrid_executions"]
        hy["mapping_executions"] = ver.get("mapping_executions")
        hy["confirm_executions"] = ver.get("confirm_executions")
        hy["kmemleak_rounds"] = ver["kmemleak_rounds"]
        hy["vm_seconds"] = round(ver["timing"].get("mapping_vm_s", 0)
                                 + ver["timing"].get("confirm_vm_s", 0), 1)
        out["approaches"]["hybrid"] = hy

        # KernelLeakGuard's complete output: confirmed static warnings plus the
        # leaks its own (module-filtered) mapping sweep left behind.
        sweep = {(s["module"], s["line"]) for s in ver.get("sweep_leaks", [])}
        comb = metrics(confirmed | sweep, gt)
        comb["executions"] = ver["hybrid_executions"]
        comb["from_sweep_only"] = sorted(f"{m}:{l}" for m, l in sweep - confirmed)
        out["approaches"]["klg/combined"] = comb

        triage: dict[str, dict[str, int]] = {}
        for v in ver["verdicts"]:
            c = cand[v["id"]]
            label = gt.get((c["module"], c["alloc"]["line"]))
            truth = label.label if label else "UNKNOWN"
            triage.setdefault(v["status"], {}).setdefault(truth, 0)
            triage[v["status"]][truth] += 1
        out["triage"] = triage

        for name in ("exhaustive", "random"):
            if name not in ver.get("baselines", {}):
                continue
            b = ver["baselines"][name]
            m = metrics({(s["module"], s["line"]) for s in b["sites"]}, gt)
            m["executions"] = b["executions"]
            out["approaches"][f"dynamic/{name}"] = m
        if "dynamic/exhaustive" in out["approaches"]:
            out["approaches"]["dynamic/exhaustive"]["vm_seconds"] = round(
                ver["timing"].get("sweep_vm_s", 0), 1)

    cpp = cppcheck_sites(src_dir)
    if cpp is not None:
        out["approaches"]["cppcheck"] = metrics(cpp, gt)

    (config.RESULTS / "evaluation.json").write_text(json.dumps(out, indent=2))
    return out


def summary_table(ev: dict) -> str:
    rows = ["| Approach | TP | FP | FN | Precision | Recall | F1 |",
            "|---|---|---|---|---|---|---|"]
    for name, m in ev["approaches"].items():
        rows.append(f"| {name} | {m['tp']} | {m['fp']} | {m['fn']} | {m['precision']:.2f} | "
                    f"{m['recall']:.2f} | {m['f1']:.2f} |")
    return "\n".join(rows)
