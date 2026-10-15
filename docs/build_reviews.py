"""Generate the Project Proposal and the Project Design & Progress Report
(Review-I) on the VIT cover page.

    .venv/bin/python docs/build_reviews.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from docx import Document

sys.path.insert(0, str(Path(__file__).resolve().parent))
import report_lib as R  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DOCS, FIG, RES = ROOT / "docs", ROOT / "docs" / "figures", ROOT / "results"
TITLE = ("KernelLeakGuard: Hybrid Static Analysis and Runtime Verification of "
         "Memory Leaks in Linux Kernel Early-Exit Paths")
TEAM = [("Om Gunjan Gupta", "24BIT0316"), ("Abhishek Kumar Singh", "24BIT0309"),
        ("Aarav Jain", "24BIT0023")]


def cover(kind: str) -> tuple[Document, R.Writer]:
    doc = Document(DOCS / "templates" / "OS_Project_Report_Template.docx")
    R.setup_styles(doc)
    for p in doc.paragraphs:
        t = p.text.strip()
        if t == "PROJECT REPORT":
            R.set_runs(p, kind)
        elif t == "TITLE OF THE PROJECT":
            R.set_runs(p, TITLE)
            for r in p.runs:
                r.font.size = R.Pt(17)
                r.font.color.rgb = R.RGBColor(0, 0, 0)
    rows = [p for p in doc.paragraphs if p.text.strip().startswith("Student Name")]
    for p, (n, reg) in zip(rows, TEAM):
        R.set_runs(p, f"{n}\t\t\t\t{reg}")
        for r in p.runs:
            r.font.color.rgb = R.RGBColor(0, 0, 0)
    R.tighten_cover(doc)
    decl = next(p for p in doc.paragraphs if p.text.strip() == "DECLARATION")
    R.remove_from(doc, decl._p)
    return doc, R.Writer(doc)


def finish(doc, name):
    R.page_numbers(doc)
    out = DOCS / name
    doc.save(out)
    print(f"wrote {out}")


# ============================================================== PROPOSAL ====
doc, w = cover("PROJECT PROPOSAL")
w.chapter_heading(None, "Project Proposal")
w.chapter = 1


class _Flow:
    """Proposal sections are short: numbered level-2 headings, no page breaks."""

    def __init__(self, writer):
        self.w = writer

    def chapter_heading(self, number, title):
        self.w.chapter = number
        return self.w.h2(f"{number}. {title}")

    def __getattr__(self, name):
        return getattr(self.w, name)


w = _Flow(w)
w.chapter_heading(1, "Problem Statement")
w.para(
    "Linux kernel routines exit early when an allocation or a device operation fails. Each "
    "early exit must release everything acquired so far; a forgotten kfree() leaks kernel "
    "memory permanently. Because such paths run only when something fails, testing rarely "
    "executes them, and static analysers report many warnings that are not real leaks. The "
    "problem addressed is: find memory leaks on kernel early-exit paths and automatically "
    "verify each finding by reproducing the failure in an isolated virtual machine, so that "
    "only evidence-backed leaks reach the developer.")
w.chapter_heading(2, "Objectives")
w.bullets([
    "Implement an LLVM-based static analyser (C++) that detects allocations neither freed nor "
    "handed over on paths to a function exit, inspired by MLEE (USENIX ATC 2021).",
    "Identify, for each warning, the failing call that leads onto the leaking path.",
    "Build an isolated QEMU/KVM Linux test environment with kmemleak and fault injection.",
    "Inject the predicted failure automatically and classify each warning as confirmed, not "
    "reproduced or inconclusive using kmemleak evidence.",
    "Evaluate on a benchmark of kernel modules with ground truth (static vs hybrid vs "
    "dynamic-only) and provide a dashboard.",
], numbered=True)
w.chapter_heading(3, "Scope")
w.para("In scope: loadable kernel modules compiled with clang for Linux 6.18 LTS; kmalloc, "
       "vmalloc, kvmalloc and slab-cache allocations and their release functions; failures "
       "injectable with failslab, fail_function and fail_usercopy; a benchmark corpus written "
       "by the team. Out of scope: analysis of the complete kernel, non-memory resources, "
       "hardware-dependent drivers, and recreating MLEE's full research system.")
w.chapter_heading(4, "Literature / Background")
w.para("MLEE (Wang, 2021) detects missing releases on early-exit paths statically and found "
       "120 new Linux leaks but leaves confirmation to developers. Hector (Saha et al., DSN "
       "2013), K-MELD (Emamdoost et al., NDSS 2021) and HERO (Wu et al., USENIX Security 2021) "
       "are further static approaches. FIFUZZ (Jiang et al., USENIX Security 2020) and "
       "syzkaller with kmemleak execute error paths dynamically but only find leaks on paths "
       "they reach and give no static root cause. Linux provides kmemleak (a tracing "
       "mark-and-sweep leak detector) and a fault-injection framework (failslab, "
       "fail_function, fail_usercopy, per-task fail-nth). The proposed work combines "
       "static prediction with targeted fault injection and kmemleak.")
w.chapter_heading(5, "Methodology")
w.bullets([
    ("Static analysis: ", "compile modules to LLVM IR with the exact kbuild flags; track "
     "allocations through aliases and stack objects; classify releases and ownership "
     "transfers; compute function summaries; search paths from each allocation to every "
     "exit, pruning infeasible paths; report exit, error code and trigger calls."),
    ("Test environment: ", "custom Linux 6.18.55 kernel with kmemleak and fault injection, "
     "booted in QEMU/KVM from a minimal initramfs with a shared folder."),
    ("Fault-point mapping: ", "run each routine with fail-nth = 1, 2, 3 ... and map each "
     "injected fault to a source line from its stack trace."),
    ("Targeted verification: ", "inject the fault that fails the predicted trigger call, scan "
     "kmemleak, attribute leaked objects to allocation sites, decide the verdict."),
    ("Evaluation: ", "precision, recall and cost against ground truth; ablation of analysis "
     "features; comparison with dynamic-only baselines."),
], numbered=True)
w.chapter_heading(6, "Tools / Software")
w.table(["Purpose", "Tool"], [
    ["Static analysis", "C++17, LLVM/Clang 21"],
    ["Kernel and modules", "Linux 6.18.55 LTS, kbuild, kmemleak, fault injection"],
    ["Isolation", "QEMU with KVM, WSL2 on Windows 11, busybox initramfs"],
    ["Runtime agent", "C (statically linked)"],
    ["Automation, evaluation, dashboard", "Python 3, Streamlit, matplotlib"],
    ["Version control", "Git"],
], "Tools and software", widths=[6, 10])
w.chapter_heading(7, "Work Plan")
w.table(["Phase", "Activities", "Deliverable"], [
    ["1", "Literature study (MLEE, kmemleak, fault injection); environment setup; kernel build",
     "Proposal; bootable test VM"],
    ["2", "Benchmark corpus with ground truth; IR extraction; analyser core (aliases, path search)",
     "First static findings"],
    ["3", "Ownership transfer, summaries, branch correlation; in-guest agent; fault-point sweep",
     "Review-I: working prototype (60-70%)"],
    ["4", "Targeted verification, kmemleak attribution, verdicts; baselines; dashboard",
     "End-to-end pipeline"],
    ["5", "Evaluation, ablation, repeated runs; report, user manual, presentation",
     "Review-II, final report and PPT"],
], "Work plan", widths=[1.5, 10, 4.5])
w.chapter_heading(8, "Team Member Responsibilities")
w.table(["Member", "Register No.", "Responsibilities"], [
    ["Om Gunjan Gupta", "24BIT0316", "Static analyser (C++/LLVM): IR preparation, alias and ownership "
     "analysis, function summaries, path search, trigger identification"],
    ["Abhishek Kumar Singh", "24BIT0309", "Kernel configuration and build, QEMU/KVM environment, "
     "klg-agent fault-injection driver, kmemleak protocol"],
    ["Aarav Jain", "24BIT0023", "Benchmark corpus and ground truth, Python orchestrator and "
     "verifier, evaluation, dashboard"],
], "Responsibilities", widths=[3.5, 2.5, 10])
finish(doc, "KernelLeakGuard_Project_Proposal.docx")

# ============================================================ REVIEW-I ======
doc, w = cover("PROJECT DESIGN & PROGRESS REPORT (REVIEW-I)")
w = w.w if isinstance(w, _Flow) else w
w.chapter_heading(1, "System Architecture")
w.para("KernelLeakGuard has a static part on the host and a dynamic part inside a QEMU/KVM "
       "guest. Static candidates, including the source line of each predicted failing call, "
       "drive fault injection in the guest; kmemleak provides the evidence for the verdict.")
w.figure(FIG / "fig_architecture.png", "System architecture", 16.5)
w.chapter_heading(2, "Module Design")
w.table(["Module", "Input", "Output", "Owner"], [
    ["IR generation (klg/build.py)", "module source, kbuild .cmd files", "LLVM bitcode (.bc)", "Aarav Jain"],
    ["Static analyser (analyzer/)", "bitcode, API specification", "candidates JSON", "Om Gunjan Gupta"],
    ["Guest kernel & VM (vm/)", "kernel config fragment", "bzImage, initramfs, VM runs", "Abhishek Kumar Singh"],
    ["klg-agent (runtime/)", "target routine, fault number", "attempt log with fault stacks", "Abhishek Kumar Singh"],
    ["Verifier (klg/verify.py)", "candidates, agent logs, kmemleak", "verdicts with evidence", "Aarav Jain"],
    ["Evaluation & dashboard", "verdicts, ground truth", "metrics, charts, web UI", "Aarav Jain"],
], "Modules and interfaces", widths=[4.5, 4.3, 4.2, 3.0], size=9)
w.para("**Data storage.** No database is needed. Every stage writes JSON files under "
       "results/: static findings per module (results/static/<variant>/<module>.json), "
       "verification results with evidence (results/runtime/verification.json) and metrics "
       "(results/evaluation.json). A static finding contains the function, allocator, "
       "allocation and exit locations, return value, triggers, confidence and path lines.")
w.chapter_heading(3, "Algorithms and Flowcharts")
w.para("**Static leak detection.** For each allocation the analyser computes the values that "
       "may hold the pointer, marks instructions that release it or transfer ownership, and "
       "searches paths to every return. The edge on which the allocation failed and paths "
       "that contradict an earlier branch decision are pruned; a path reaching a return "
       "without a release or transfer is reported with the failing calls that guard it.")
w.code(size=8, text="""\
for each allocation a in F:
    Alias  := values that may hold a (casts, GEPs, PHIs, stack fields)
    Events := releases (kfree, wrappers) ∪ transfers (non-local store, return, capture)
    DFS from a:  stop at Events; skip "a == NULL" edge; skip contradictory branches
                 at a return → report (alloc, exit, return value, trigger calls)""")
w.figure(FIG / "fig_flowchart.png", "Flowchart of runtime verification", 11.5)
w.chapter_heading(4, "Implementation Progress")
w.table(["Component", "Status"], [
    ["Kernel 6.18.55 with kmemleak + fault injection, QEMU/KVM boot (~2 s)", "Completed"],
    ["Benchmark corpus: 32 modules with ground truth", "Completed"],
    ["Static analyser: aliases, ownership transfer, summaries, path search, triggers", "Completed"],
    ["klg-agent: fail-nth sweep and targeted repeat", "Completed"],
    ["Fault-point to source-line mapping (faddr2line)", "Completed"],
    ["Targeted confirmation with kmemleak and verdicts", "Working prototype"],
    ["Dynamic baselines, ablation, repeated runs", "In progress (Review II)"],
    ["Dashboard, report, user manual, presentation", "In progress (Review II)"],
], "Implementation status at Review-I", widths=[12, 4])
w.para("The core functionality is executable end to end: `python3 -m klg all` builds the "
       "corpus, runs the analyser and verifies the warnings inside the virtual machine.")
w.h2("Screenshots")
for name, cap in (("shot_pipeline.png", "Running the complete pipeline"),
                  ("shot_findings.png", "Findings with runtime verdicts"),
                  ("shot_agent.png", "klg-agent injecting a failure inside the guest"),
                  ("shot_kmemleak.png", "kmemleak reporting the leaked object")):
    if (FIG / name).exists():
        w.figure(FIG / name, cap, 16)
w.chapter_heading(5, "Challenges Faced")
w.table(["Challenge", "Cause", "Solution"], [
    ["Every kmalloc() appeared twice in the IR", "kmalloc's macro tests "
     "mem_alloc_profiling_enabled() even when profiling is off", "Fold constant-returning stubs "
     "and remove dead branches before analysis"],
    ["Correlated conditions reported as leaks", "Path search started at the allocation and "
     "ignored the guarding condition", "Seed the search with dominating branch decisions"],
    ["Loop leak missed", "Decisions from iteration 1 applied to iteration 2", "Mark decisions "
     "stale when a path goes round a loop again"],
    ["fail_function ignored fail-nth", "int3 kprobe handlers run in NMI-like context where "
     "in_task() is false", "Enable ftrace-based kprobes (KPROBES_ON_FTRACE)"],
    ["Guest kernel panic in random baseline", "Probability raised before task filter, faulting PID 1",
     "Enable task-filter first; agent enables faults only around the target syscall"],
    ["Fault sites not symbolised", "faddr2line rejects frames whose kallsyms size includes "
     "padding", "Pass func+offset without size"],
    ["Unrolled loop frames had no source line", "Merged debug locations", "Fall back to the "
     "function's single allocation site"],
    ["Leak hidden in some runs (klg_l17)", "Stale pointer copies on reused stacks and in reused "
     "slab objects", "KSTACK_ERASE, no task-stack scan, init_on_alloc/init_on_free"],
], "Challenges and solutions", widths=[4.3, 5.7, 6], size=9)
finish(doc, "KernelLeakGuard_Review1_Design_Progress.docx")
