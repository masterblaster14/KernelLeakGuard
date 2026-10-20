"""Generate docs/KernelLeakGuard_Final_Report.docx from the VIT template.

    .venv/bin/python docs/build_report.py

Keeps the template's cover page and declaration (filled in), replaces the
placeholder body with the report, and reads every number from results/.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import report_lib as R  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
FIG = DOCS / "figures"
RES = ROOT / "results"

TITLE = ("KernelLeakGuard: Hybrid Static Analysis and Runtime Verification of "
         "Memory Leaks in Linux Kernel Early-Exit Paths")
TEAM = [("Om Gunjan Gupta", "24BIT0316"), ("Abhishek Kumar Singh", "24BIT0309"),
        ("Aarav Jain", "24BIT0023")]

ev = json.loads((RES / "evaluation.json").read_text())
ver = json.loads((RES / "runtime" / "verification.json").read_text())
static = {p.stem: json.loads(p.read_text()) for p in sorted((RES / "static" / "full").glob("*.json"))}
A = ev["approaches"]
GT = ev["ground_truth"]
runs = sorted((RES / "runs").glob("evaluation_*.json")) if (RES / "runs").exists() else []
run_evs = [json.loads(p.read_text()) for p in runs]


def pct(x):
    return f"{100 * x:.0f}%"


def m(name, key):
    return A[name][key]


def count_status(s):
    return sum(1 for v in ver["verdicts"] if v["status"] == s)


n_warn = sum(len(r["candidates"]) for r in static.values())
n_conf, n_ref, n_inc = count_status("confirmed"), count_status("not-reproduced"), count_status("inconclusive")
an_ms = m("static/full", "analysis_ms")
sites_total = sum(r["stats"]["alloc_sites"] for r in static.values())
funcs_total = sum(r["stats"]["functions"] for r in static.values())
vm_sweep = ver["timing"].get("sweep_vm_s", 0)
vm_conf = ver["timing"].get("confirm_vm_s", 0)
vm_map = ver["timing"].get("mapping_vm_s", 0)
fp_removed = A["static/full"]["fp"] - A["hybrid"]["fp"]
fixes_path = RES / "fixes" / "fixes.json"
fixes = json.loads(fixes_path.read_text()) if fixes_path.exists() else []
fix_main = [f for f in fixes if f["status"] in ("validated", "runtime-validated", "failed", "skipped")]
n_fix = len(fix_main)
n_fix_ok = sum(1 for f in fix_main if f["status"] == "validated")
n_fix_rt = sum(1 for f in fix_main if f["status"] == "runtime-validated")
# Optional Chapter 4 sections shift the "Analysis" number: 4.4 real-kernel,
# 4.5 seeded leaks (when present), then Analysis.
_rs = RES / "real" / "summary.json"
_has_real = _rs.exists() and json.loads(_rs.read_text()).get("runtime_modules")
_seed_file = RES / "seeded" / "summary.json"
seeds = json.loads(_seed_file.read_text()) if _seed_file.exists() else []
SEC_SEED = "4.5" if _has_real else "4.4"
SEC_AN = f"4.{4 + bool(_has_real) + bool(seeds)}"

# ---------------------------------------------------------------- template --
doc = Document(DOCS / "templates" / "OS_Project_Report_Template.docx")
R.setup_styles(doc)
paras = doc.paragraphs
for p in paras:
    t = p.text.strip()
    if t == "TITLE OF THE PROJECT":
        R.set_runs(p, TITLE)
        for r in p.runs:
            r.font.size = R.Pt(17)
            r.font.color.rgb = R.RGBColor(0, 0, 0)
    elif "declare that the project report titled" in t:
        for r in p.runs:
            r.text = re.sub(r"_{5,}", TITLE, r.text)
student_rows = [p for p in paras if p.text.strip().startswith("Student Name")]
for p, (name, reg) in zip(student_rows, TEAM):
    R.set_runs(p, f"{name}\t\t\t\t{reg}")
    for r in p.runs:
        r.font.color.rgb = R.RGBColor(0, 0, 0)


R.tighten_cover(doc)


def corpus_sources(prefix="klg_"):
    return [p for p in sorted((ROOT / "corpus").glob(f"{prefix}*.c")) if ".mod." not in p.name]

# Replace the manual TOC table with a real TOC field; drop the placeholder body.
toc_head = next(p for p in paras if p.text.strip() == "TABLE OF CONTENTS")
toc_table = doc.tables[0]._tbl
toc_table.getparent().remove(toc_table)
toc_p = doc.add_paragraph()
toc_head._p.addnext(toc_p._p)
R.toc_field(toc_p)
abstract_head = next(p for p in doc.paragraphs if p.text.strip() == "ABSTRACT")
R.remove_from(doc, abstract_head._p)

w = R.Writer(doc)

# ---------------------------------------------------------------- abstract --
w.chapter_heading(None, "Abstract")
w.para(
    "Operating system kernels must release every resource they acquire, including on the "
    "rarely executed error paths that run when an allocation or a device operation fails. "
    "A forgotten kfree() on such an early-exit path leaks kernel memory that can never be "
    "reclaimed, causing memory pressure, degraded performance and, when an attacker can "
    "trigger the failure repeatedly, denial of service. Because these paths execute only "
    "when something goes wrong, ordinary testing almost never exercises them, and static "
    "analysers that do inspect them report many warnings that turn out to be safe.")
w.para(
    "KernelLeakGuard combines both worlds. An LLVM-based static analyser written in C++, "
    "inspired by MLEE (USENIX ATC 2021), tracks every kernel allocation through aliases, "
    "stack objects and function calls, understands ownership transfer, and searches for "
    "paths from an allocation to a function exit that neither free nor hand over the "
    "memory. For each warning it identifies the failing call that leads onto the leaking "
    "path. A runtime verifier then boots a custom Linux 6.18.55 kernel under QEMU/KVM, uses "
    "the kernel's per-task fault injection (fail-nth) to fail exactly that call, and asks "
    "the kernel memory leak detector (kmemleak) whether an object allocated at the reported "
    "site was left unreferenced. Every warning is labelled confirmed, not reproduced or "
    "inconclusive, with stack-trace evidence.")
w.para(
    f"On a benchmark of {GT['modules']} kernel modules with {GT['leak_sites']} leaking and "
    f"{GT['safe_sites']} safe allocation sites, the static analyser reaches precision "
    f"{m('static/full', 'precision'):.2f} and recall {m('static/full', 'recall'):.2f} "
    f"(a naive missing-kfree analysis: precision {m('static/naive', 'precision'):.2f}). "
    f"Runtime verification confirmed {n_conf} of {n_warn} warnings with kernel evidence and "
    f"raised precision to {m('hybrid', 'precision'):.2f} with no false confirmations. "
    f"Together with the leaks its own fault-point sweep exposes, KernelLeakGuard finds "
    f"{m('klg/combined', 'tp')} of the {GT['leak_sites']} leaks with no false positive "
    f"(F1 {m('klg/combined', 'f1'):.2f}), using {m('hybrid', 'executions')} executions of "
    f"kernel routines in total against {m('dynamic/exhaustive', 'executions')} for "
    f"exhaustive fault injection (F1 {m('dynamic/exhaustive', 'f1'):.2f}) and "
    f"{m('cppcheck', 'f1'):.2f} F1 for the cppcheck analyser. For "
    f"{n_fix_ok} of {n_fix} confirmed leaks it generates a fix patch validated by compilation, "
    f"re-analysis and an exhaustive re-run in the VM. The complete pipeline runs in about "
    f"{round((vm_sweep + vm_map + vm_conf) / 60 + 0.5)} minutes on a laptop.")
if _has_real:
    _ab_real = json.loads(_rs.read_text())
    _ab_conf = sorted([s_ for s_ in seeds if s_.get("confirmed")],
                      key=lambda s_: not s_.get("history"))
    w.para(
        f"On {_ab_real['modules']} real Linux modules, general precision refinements reduced the "
        f"static warnings from 115 to {_ab_real['warnings']} without changing any benchmark "
        "result"
        + ((f", and a real historical leak in {_ab_conf[0]['module']} (fixed upstream by commit "
            f"{_ab_conf[0]['history']['commit']}), re-introduced into today's code, was detected, "
            "confirmed in the VM with kmemleak and fixed end to end"
            if _ab_conf[0].get("history") else
            f", and a seeded early-exit leak in real {_ab_conf[0]['module']} code was detected, "
            "confirmed in the VM and fixed end to end") if _ab_conf else "")
        + ". The tool also found five defects in the kernel itself, all still present in "
        "mainline: a slab-cache leak in the SLUB allocator, exposed by fault injection during "
        "the initialisation of erofs, f2fs, hfsplus and nilfs2, and a leak in f2fs introduced "
        "by a 2026 fix, both with fixes validated in the VM; memory leaks in ntfs3's log replay "
        "and in ufs's truncation (reported in 2018 but never fixed), found statically, with "
        "fixes that remove the warnings; and a use-after-free of module memory when a module's "
        "initialisation fails after it added a disk.")

# ------------------------------------------------------------ chapter 1 -----
w.chapter_heading(1, "Introduction")
w.h2("1.1 Motivation")
w.para(
    "The Linux kernel manages memory for itself through allocators such as kmalloc(), "
    "kzalloc(), vmalloc() and dedicated slab caches. Unlike user programs, the kernel has no "
    "garbage collector and no process exit that returns everything to the system: memory "
    "that a kernel routine allocates and then loses track of stays allocated until the "
    "machine reboots. Long-running servers, phones and embedded devices therefore suffer "
    "from even small leaks when the leaking code runs repeatedly.")
w.para(
    "A large share of kernel leaks hide on early-exit paths. Kernel code checks the result of "
    "almost every operation and returns an error code such as -ENOMEM or -EINVAL as soon as "
    "something fails, usually through a ladder of goto labels that undo the work done so far. "
    "Getting every exit right is error-prone: jumping to the wrong label, adding a new exit "
    "without the matching cleanup, or forgetting that an earlier allocation is still owned by "
    "the function are all common mistakes. Wang (MLEE, 2021) reported 120 previously unknown "
    "leaks of exactly this kind in the Linux kernel, and syzbot, Google's continuous kernel "
    "fuzzing service, files kmemleak reports every week.")
w.para(
    "The difficulty is that these paths run only when an allocation or a device operation "
    "fails, which practically never happens in testing. Static analysis can inspect every "
    "path but cannot tell whether memory is really lost, since ownership may move to a list, "
    "a caller or an asynchronous callback. Dynamic tools such as kmemleak give hard evidence "
    "but only for paths that actually execute. This project brings the two together so that "
    "static warnings become reproducible, evidence-backed bug reports.")
w.h2("1.2 Scope")
w.para("**Application areas.** Kernel and driver developers reviewing error handling; "
       "maintainers triaging static-analysis warnings; continuous-integration pipelines that "
       "test kernel modules; education in kernel memory management and fault handling.")
w.para("**Boundaries.** The analyser processes loadable kernel modules compiled with clang "
       "against Linux 6.18.55. It tracks the kmalloc, vmalloc, kvmalloc and slab-cache "
       "families, duplication helpers (kstrdup, kmemdup, kasprintf) and module-local wrappers. "
       "Device-managed (devm_*) memory is treated as released by the driver core. Runtime "
       "verification covers code reachable from a module's initialisation or from a debugfs "
       "trigger, with failures injectable through failslab, fail_function or fail_usercopy. "
       "The project reimplements a focused subset of MLEE-style analysis; it does not analyse "
       "the whole kernel and does not claim to replace MLEE's full system.")
w.h2("1.3 Problem Statement")
w.para(
    "Given the source code of a Linux kernel module, find allocations that are neither "
    "released nor handed over to another owner on some path to a function exit, especially "
    "on error paths; and for each such warning, automatically reproduce the failure that "
    "leads onto the path inside an isolated virtual machine and determine from kernel "
    "evidence whether memory is actually leaked, so that only confirmed leaks reach the "
    "developer and every report carries the reproduction steps.")
w.h2("1.4 Objectives")
w.bullets([
    "Build a static analyser on LLVM IR that detects missing releases on early-exit paths, "
    "with alias, ownership-transfer, interprocedural and path-correlation analysis to keep "
    "false positives low.",
    "For every warning, identify the failing call (allocation, user copy or error-returning "
    "function) whose failure steers execution onto the leaking path.",
    "Build an isolated QEMU/KVM test environment with a custom kernel that provides kmemleak "
    "and deterministic per-task fault injection.",
    "Automatically map fault points to source lines, inject the predicted failure, and decide "
    "confirmed / not reproduced / inconclusive from kmemleak evidence.",
    "Evaluate against a benchmark with known ground truth, comparing static-only, hybrid and "
    "dynamic-only approaches on precision, recall and cost, with an ablation study.",
    "Provide a command-line tool and a dashboard that present findings, source context, "
    "runtime evidence and suggested fixes.",
], numbered=True)
w.h2("1.5 Organization of the Report")
w.para("Chapter 2 surveys research on kernel leak detection, error-handling bugs and fault "
       "injection and identifies the gap this project addresses. Chapter 3 presents the "
       "architecture, each module, the algorithms with pseudo-code, the benchmark corpus and "
       "the tools used. Chapter 4 describes the experimental setup and reports the results, "
       "performance and their analysis. Chapter 5 concludes and outlines future work. "
       "References follow in MLA format.")

# ------------------------------------------------------------ chapter 2 -----
w.chapter_heading(2, "Literature Survey")
w.h2("2.1 Overview")
w.para(
    "Research relevant to this project falls into three groups: static detectors for memory "
    "leaks and resource-release bugs, studies and tools specific to error-handling code in "
    "operating systems, and dynamic techniques (fault injection, fuzzing and leak detectors) "
    "that execute error paths. Classic static leak detectors for user programs, such as "
    "the path-sensitive analysis of Xie and Aiken, the guarded value-flow analysis of Cherem "
    "et al. and SABER by Sui et al., established the core idea of following an allocated "
    "value to the points where it is released. Kernel code adds its own challenges: huge "
    "code bases, macro-heavy APIs, ownership passed through structures and callbacks, and "
    "error handling as the dominant source of bugs, which Palix et al. found to be a major "
    "category of faults in Linux.")
w.h2("2.2 Review of Existing Methods")
reviews = [
    ("MLEE (Wang, USENIX ATC 2021). ",
     "MLEE compiles the kernel to LLVM IR, identifies early-exit paths with control-flow "
     "analysis, and reports allocations that are released on normal paths but not on "
     "early-exit paths. Liveness, validity, usage, alias and interprocedural checks remove "
     "spurious cases. MLEE found 120 new leaks in Linux. Its reports are static warnings: "
     "developers must still decide manually whether each one is real, and the paper does not "
     "reproduce the failures."),
    ("Hector (Saha et al., DSN 2013). ",
     "Hector looks for resource-release omissions in error-handling code by comparing the "
     "resources released along different error paths of the same function, and found "
     "hundreds of faults in Linux and other systems code. Like MLEE it is purely static and "
     "reports candidates that require manual confirmation."),
    ("K-MELD (Emamdoost et al., NDSS 2021). ",
     "K-MELD detects kernel memory leaks in specialised modules by learning which functions "
     "allocate and release memory and reasoning about ownership transfer, using a rule "
     "derived from the uses of each allocated object. It addresses the custom allocator "
     "problem but remains a static approach."),
    ("HERO (Wu et al., USENIX Security 2021). ",
     "HERO identifies precise pairs of functions (for example allocate/release, "
     "register/unregister) and detects disordered or missing error handling relative to "
     "those pairs, reporting many confirmed bugs in Linux. It shows that understanding "
     "pairing and ownership is essential for low false-positive rates."),
    ("FIFUZZ (Jiang et al., USENIX Security 2020). ",
     "FIFUZZ fuzzes error-handling code with context-sensitive software fault injection: it "
     "decides at run time which failure sites to trigger based on calling context, "
     "exploring error paths that random fault injection rarely reaches. It finds crashes "
     "rather than linking failures to static leak warnings."),
    ("syzkaller and kmemleak. ",
     "syzkaller is a coverage-guided kernel fuzzer that, in syzbot, combines systematic fault "
     "injection through fail-nth with kmemleak scans to report leaks continuously. Leaks are "
     "found only on paths that fuzzing happens to reach, and each report is a backtrace "
     "without a root-cause explanation of which exit forgot the release."),
    ("Coccinelle and Smatch (Lawall and Muller, USENIX ATC 2018). ",
     "Semantic-patch matching and pattern checkers are used daily by kernel developers to find "
     "and fix error-handling mistakes. They are fast and precise for known patterns but "
     "cannot reason about arbitrary ownership flows."),
]
for head, text in reviews:
    w.para(text, bold_prefix=head)
w.h2("2.3 Comparative Analysis")
w.table(["Paper", "Technique Used", "Dataset", "Advantages", "Limitations"], [
    ["MLEE (2021)", "LLVM IR, early-exit vs normal-path release comparison", "Linux kernel",
     "Kernel scale; 120 new leaks", "Static only; manual triage of reports"],
    ["Hector (2013)", "Intra-procedural comparison of error paths", "Linux, PHP, Python, etc.",
     "Finds release omissions without specifications", "False positives; no reproduction"],
    ["K-MELD (2021)", "Ownership reasoning, allocator inference", "Linux modules",
     "Handles custom allocators", "Static only"],
    ["HERO (2021)", "Function pairing, error-handling order", "Linux, FreeBSD, OpenSSL",
     "Precise pairs; many confirmed bugs", "Needs pairs; no runtime evidence"],
    ["FIFUZZ (2020)", "Context-sensitive fault injection fuzzing", "Linux drivers, apps",
     "Executes deep error paths", "Finds crashes; leaks not root-caused"],
    ["syzkaller + kmemleak", "Coverage fuzzing, fail-nth, kmemleak", "Linux kernel (syzbot)",
     "Real evidence, continuous", "Only reached paths; backtrace without root cause"],
    ["KernelLeakGuard (this work)", "LLVM static analysis + targeted fault injection + kmemleak",
     f"{GT['modules']}-module benchmark with ground truth",
     "Evidence-backed verdicts, reproduction, root cause", "Module-level scope; failure must be injectable"],
], "Related works", widths=[2.6, 3.6, 2.8, 3.4, 3.4], size=9)
w.h2("2.4 Research Gap")
w.para(
    "Static detectors (MLEE, Hector, K-MELD, HERO) cover all paths but leave every warning to "
    "manual triage, and their false positives come precisely from situations that are hard "
    "to decide statically: ownership handed to lists or callers, loop rollbacks, correlated "
    "conditions. Dynamic approaches (fault injection, syzkaller with kmemleak) provide real "
    "evidence but only for paths they happen to execute, and their reports lack the static "
    "root cause: which exit, which missing release, which failing call. None of the surveyed "
    "systems uses the static analysis to drive targeted fault injection for each warning and "
    "feeds the kernel's own leak evidence back into the verdict.")
w.para(
    "KernelLeakGuard fills this gap with a closed loop: the static analyser predicts the "
    "failing call for every warning, the runtime verifier fails exactly that call in a VM, "
    "and kmemleak decides. This turns static warnings into confirmed, reproducible reports "
    "and identifies refuted ones, while keeping the root-cause explanation that dynamic "
    "tools lack. We present this integration as our contribution and evaluate it "
    "empirically; we do not claim it is globally novel without a broader survey.")

# ------------------------------------------------------------ chapter 3 -----
w.chapter_heading(3, "Proposed Technique")
w.h2("3.1 System Architecture")
fig_arch = w.next_figure()
w.para(f"{fig_arch} shows the architecture. The pipeline has a static half that runs on the "
       "host and a dynamic half that runs inside a QEMU/KVM virtual machine; the static "
       "candidates (including the line of each trigger call) drive the dynamic half.")
w.figure(FIG / "fig_architecture.png", "Architecture of KernelLeakGuard", 16.5)
w.para("**Workflow.**")
w.bullets([
    "Each module is compiled by kbuild; its exact compile command is re-run with "
    "`-emit-llvm` to obtain LLVM bitcode that sees the same headers, macros and configuration.",
    "`klg-analyze` reports candidate leaks: allocation site, leaking exit, returned value, the "
    "trigger calls whose failure leads to the exit, and a confidence level.",
    "Sweep run: in the VM, `klg-agent` executes each routine with fail-nth = 1, 2, 3 ... and "
    "records the stack trace of each injected fault, producing a map from fault number to "
    "source line.",
    "Confirmation run: for every candidate, the fault number that hits its trigger line is "
    "injected three times; kmemleak is scanned and leaked objects are attributed to "
    "allocation sites through stack symbolisation (faddr2line).",
    "Verdicts and evidence are written to JSON, evaluated against ground truth, and shown in "
    "the dashboard.",
], numbered=True)
w.h2("3.2 Module-wise Description")
w.h3("3.2.1 Static analyser (klg-analyze, C++/LLVM) - Om Gunjan Gupta")
w.para(
    "The analyser loads bitcode produced with clang's -O2 front end but no LLVM optimisation "
    "passes, so the IR keeps the program structure as written. A preparation step promotes "
    "stack variables to SSA registers (mem2reg), folds configuration stubs such as "
    "mem_alloc_profiling_enabled() that kmalloc()'s macro tests, and removes the resulting "
    "dead branches. Allocation sites are calls to the allocator functions of the API "
    "specification (kmalloc, kzalloc, kcalloc, kvmalloc, vmalloc, kmem_cache_alloc, kstrdup, "
    "kmemdup, kasprintf, memdup_user and their variants) or to module functions whose "
    "summary says they return fresh memory.")
w.bullets([
    ("Alias tracking: ", "the allocated pointer is followed through casts, GEPs, PHIs and "
     "selects, and field-sensitively through local stack objects (structures and arrays) "
     "from which it is reloaded."),
    ("Release and ownership transfer: ", "kfree() and its relatives release the object; a "
     "store into non-local memory, returning the pointer, or passing it to a function that "
     "captures it transfers ownership and ends the function's responsibility."),
    ("Function summaries: ", "for each module function and each pointer parameter a monotone "
     "fixpoint computes whether it frees, captures or returns the parameter, and whether it "
     "provably publishes it (stores it into a list, hash table, global or another object, "
     "directly or through a module helper such as list_add_tail()). A second fixpoint marks "
     "functions that return new memory (allocation wrappers), but only when the new object is "
     "not published first: a helper that links the object into a list or returns a shared, "
     "reference-counted one is a lookup, and the caller does not own the result."),
    ("Path search: ", "a depth-first search from the allocation to every return, pruning the "
     "edge on which the allocation itself failed (a NULL check, or an IS_ERR() check when the "
     "value is an ERR_PTR error code) and edges that contradict an earlier decision on the same "
     "condition (branch correlation, seeded with the dominating conditions that guard the "
     "allocation). Values are resolved along the current path: a return of phi(object, NULL) "
     "hands the object over only on the paths that bring it into the phi, and a switch whose "
     "selector is a constant on the path (the cleanup-destination switch clang emits for a "
     "goto out of a scoped block) has a single feasible successor. Loops are unrolled twice; "
     "a second execution of the allocation creates a new instance while the earlier one stays "
     "reachable through memory."),
    ("Reporting: ", "the returned value on the path is resolved (constant errno, NULL, or a "
     "propagated error code) to classify error exits; the failing calls that guard the "
     "path become triggers; confidence is high when the function frees the object on "
     "another path and the leaking path returns an error."),
])
w.h3("3.2.2 Guest kernel and virtual machine - Abhishek Kumar Singh")
w.para(
    "Linux 6.18.55 LTS is built with clang from defconfig, the KVM guest fragment and the "
    "KernelLeakGuard fragment (vm/kernel.config.fragment): kmemleak without automatic "
    "scanning, fault injection with failslab, fail_function and fail_usercopy, ftrace-based "
    "kprobes and virtio-9p sharing. Several settings make kmemleak trustworthy by removing "
    "stale copies of pointers that would make a leaked object look referenced: thread stacks "
    "come from the page allocator (CONFIG_VMAP_STACK=n), kernel stacks are erased on return to "
    "user space (CONFIG_KSTACK_ERASE), kmemleak does not scan task stacks, and slab memory is "
    "zeroed on allocation and free (init_on_alloc=1 init_on_free=1). The guest boots from a "
    "busybox initramfs in about two seconds, mounts the host directory over 9p, configures "
    "fault injection through debugfs and runs the job script generated by the host.")
w.h3("3.2.3 Fault-injection agent (klg-agent, C) - Abhishek Kumar Singh")
w.para(
    "klg-agent is a statically linked C program that drives one kernel routine at a time. "
    "In sweep mode it writes N to /proc/thread-self/fail-nth, runs the routine (writing to "
    "the module's debugfs trigger file or loading the module with finit_module()), reads "
    "fail-nth back to learn whether the fault fired, and records the kernel log lines of "
    "the attempt. In repeat mode it injects a chosen fault several times and, when given "
    "the expected stack frame, verifies that the fault landed there and probes neighbouring "
    "N if fault numbering drifted between boots. A random mode enables probabilistic faults "
    "for the task only around the target system call, for the random baseline. With "
    "--filter the agent sets the fault-injection stack-trace filter (require-start / "
    "require-end) to the target module's code, so only the module's own fault points are "
    "counted; the module's layout comes from klg_modwatch, a helper kernel module that uses "
    "a module notifier to log every module's load address and function symbols. The same "
    "log lets the host resolve kmemleak backtraces of modules that were already unloaded. "
    "Before each attempt the agent writes a marker to the host, so that if the guest kernel "
    "crashes or hangs, the host records the faulting fault point, reboots the VM and resumes.")
w.h3("3.2.4 Verifier, evaluation and dashboard (Python) - Aarav Jain")
w.para(
    "The klg package builds modules and IR, runs the analyser, generates the guest job "
    "scripts, boots the VM, symbolises stack frames with the kernel's faddr2line script, "
    "plans the confirmation tests, schedules them in kmemleak rounds so that leaks can be "
    "attributed unambiguously, and computes verdicts and metrics. The Streamlit dashboard "
    "lists findings with verdicts, highlights the allocation, failing call and leaking exit "
    "in the source, shows the kmemleak backtraces, compares approaches and can run the "
    "pipeline.")
w.h3("3.2.5 Operating-system concepts used")
w.table(["OS concept", "Where it appears in the project"], [
    ["Memory management", "Kernel slab allocator (kmalloc caches, kmem_cache), vmalloc, "
     "kvmalloc; ownership and release of kernel memory; kmemleak's mark-and-scan of memory"],
    ["Error handling / fault tolerance", "Early-exit paths, errno propagation, goto cleanup "
     "ladders; failslab, fail_function and fail_usercopy fault injection"],
    ["Process management", "Per-task fault injection state (fail-nth, make-it-fail), task "
     "stacks, kernel/user mode transitions, stack erasing on syscall return"],
    ["Linux system programming", "System calls (write, finit_module, delete_module, pread, "
     "pwrite), /proc and debugfs interfaces, /dev/kmsg log reading"],
    ["Device management", "Loadable kernel modules, misc devices, platform drivers with "
     "device-managed (devm) memory"],
    ["Virtualisation", "QEMU with KVM hardware acceleration, virtio-9p file sharing, "
     "initramfs boot"],
    ["Synchronisation", "Mutex-protected lists, RCU-deferred freeing (kfree_rcu, call_rcu), "
     "reference counting (kref)"],
    ["Performance analysis", "Analysis time, VM time, number of executions, precision/recall"],
], "Operating-system concepts used in KernelLeakGuard", widths=[4.2, 11.8])

w.h2("3.3 Algorithms Used")
w.para("**Algorithm 1: Early-exit leak detection (per allocation site).**")
w.code(size=8, text="""\
input : function F (SSA form), allocation call a, summaries S
output: leak candidates for a

Alias   := closure of {a} over casts, GEPs, PHIs, selects, calls returning a parameter
Slots   := stack fields a is stored into;  Alias += loads from those fields
Events  := { release(i)  : i frees an alias (spec or summary)            }
         ∪ { transfer(i) : i stores an alias to non-local memory,
                           returns it, or passes it to a capturing call }
D0      := branch outcomes that dominate block(a) outside loops around a

DFS(block, decisions D, triggers T):
  for each instruction i in block:
     if i = a again: reallocated := true            # new instance, old one lives on
     if i ∈ Events (and not superseded by reallocation): return     # handled
     if i is return: report(a, exit=i, value=resolve(retval, path), T); return
  if block ends in "br c, s0, s1":
     (key, value) := normalise(c)                   # strips !, unlikely(), zext
     for each successor s with outcome v:
        if contradicts(D, key, v) and not stale: continue   # infeasible path
        if key is "alias == NULL" and v is true and not reallocated: continue
        if call f controls c and v means "f failed": T' := T + f
        DFS(s, D + (key, v), T')                     # each block ≤ 2 times per path
  else: DFS(each successor)

DFS(block(a) after a, D0, [])""")
w.para("**Algorithm 2: Runtime verification of a candidate.**")
w.code(size=8, text="""\
input : candidate C (alloc line, trigger lines, function), module M
Sweep (once per module, in VM):
   for N = 1, 2, ...: set fail-nth := N; run M's routine
       if fail-nth not consumed: break               # all fault points visited
       record stack trace of the injected fault → source lines (faddr2line)
Plan:
   P := fault numbers whose stack contains a trigger line of C      # exact
     or whose frame is C.function with C's only allocation site       # merged debug info
     or silent faults that made the routine fail                      # __GFP_NOWARN
   if P = ∅: verdict(C) := inconclusive
Confirm (one kmemleak round, ≤ 1 test per module, init-mode tests alone):
   for N in P[0..2]: repeat 3 times: inject N, check fault hit the expected frame
   wait 6 s; scan kmemleak twice; attribute each unreferenced object by backtrace
Verdict:
   confirmed      if an object allocated at C.alloc line leaked (or, for unloaded
                  modules, an object of C's allocation size leaked in an isolated round)
   not reproduced if the predicted failure was injected but nothing leaked
   inconclusive   otherwise""")
w.h2("3.4 Dataset Details")
n_l = len(corpus_sources("klg_l"))
n_s = len(corpus_sources("klg_s"))
w.para(
    f"No public dataset of kernel error-path leaks with runnable triggers and exact ground "
    f"truth exists, so we built a benchmark corpus of {GT['modules']} kernel modules: "
    f"{n_l} containing known leaks (klg_l01-l{n_l:02d}) and {n_s} leak-free modules "
    f"(klg_s01-s{n_s:02d}), several of them fixed versions of a leaky module. The patterns "
    "follow bug classes reported for Linux (wrong goto label, missing release after "
    "copy_from_user failure, leaks in loops, through wrappers, after registration "
    "failures). Every allocation site carries a ground-truth comment GT:LEAK or GT:SAFE.")
corpus_rows = []
for src in corpus_sources():
    text = src.read_text()
    desc = re.search(r"\* [LS]\d\d - (.+?)(?:\.|\n)", text)
    leaks = text.count("GT:LEAK")
    safes = text.count("GT:SAFE")
    mode = "init" if "KLG_TRIGGER" not in text else "trigger"
    corpus_rows.append([src.stem.replace("klg_", ""), desc.group(1) if desc else "", mode,
                        f"{leaks} / {safes}"])
w.table(["Module", "Pattern", "Run mode", "Leak / safe sites"], corpus_rows,
        "Benchmark corpus (dataset)", widths=[4.2, 8.0, 1.8, 2.0], size=8.5)
w.table(["Attribute", "Description", "Type"], [
    ["Dataset source", "Written for this project (corpus/), GPL-2.0 kernel test modules", "C source"],
    ["Number of records", f"{GT['sites']} annotated allocation sites in {GT['modules']} modules "
     f"({GT['leak_sites']} leaking, {GT['safe_sites']} safe)", "integer"],
    ["Module", "kernel module name", "string"],
    ["Allocation site", "source line of the allocation call", "integer"],
    ["Label", "GT:LEAK or GT:SAFE", "categorical"],
    ["Run mode", "trigger (debugfs file) or init (module_init)", "categorical"],
], "Dataset information", widths=[3.5, 9.5, 3.0])
w.h2("3.5 Tools and Technologies")
w.table(["Area", "Tools"], [
    ["Static analysis", "C++17, LLVM/Clang 21.1.8 (IR, PassBuilder, DominatorTree, LoopInfo, JSON)"],
    ["Kernel", "Linux 6.18.55 LTS built with LLVM=1; kmemleak; failslab, fail_function, "
     "fail_usercopy; ftrace kprobes; KSTACK_ERASE"],
    ["Virtualisation", "QEMU 10 with KVM on WSL2 (Windows 11), virtio-9p, busybox initramfs"],
    ["Runtime agent", "C (static glibc), /proc/thread-self/fail-nth, /dev/kmsg"],
    ["Orchestration", "Python 3 (klg package), kernel scripts/faddr2line, binutils"],
    ["Presentation", "Streamlit, Altair, pandas, matplotlib, python-docx, python-pptx"],
    ["Version control", "Git"],
], "Tools and technologies", widths=[3.5, 12.5])
w.para("**Module division among team members.**")
w.table(["Member", "Register No.", "Modules"], [
    ["Om Gunjan Gupta", "24BIT0316", "Static analyser: IR preparation, alias/escape analysis, function "
     "summaries, path search, trigger identification, ablation options"],
    ["Abhishek Kumar Singh", "24BIT0309", "Guest kernel configuration and build, initramfs and "
     "QEMU launcher, klg-agent fault-injection driver, kmemleak protocol"],
    ["Aarav Jain", "24BIT0023", "Benchmark corpus and ground truth, Python orchestrator "
     "(symbolisation, test planning, verdicts), evaluation, dashboard"],
], "Module division", widths=[3.5, 2.5, 10.0])

# ------------------------------------------------------------ chapter 4 -----
w.chapter_heading(4, "Results and Discussion")
w.h2("4.1 Experimental Setup")
w.table(["Component", "Configuration"], [
    ["Host", "Laptop, AMD Ryzen 7 250 (8 cores / 16 threads), 15 GB RAM, Windows 11"],
    ["Linux environment", "WSL2, Ubuntu 26.04 LTS (kernel 6.18 WSL), /dev/kvm available"],
    ["Guest VM", "QEMU/KVM, 2 vCPUs, 2 GB RAM, Linux 6.18.55 (custom configuration)"],
    ["Compiler", "Clang/LLVM 21.1.8 for kernel, modules, IR and analyser"],
    ["Verification parameters", "3 executions per test, up to 3 fault points per candidate, "
     "kmemleak settle time 6 s, 2 scans per round"],
    ["Baselines", "static/naive (all refinements off); cppcheck 2.19 with a kmalloc/kfree "
     "library model; dynamic exhaustive single-fault injection; dynamic random injection "
     "(10%, 50 executions per module)"],
], "Experimental setup", widths=[4.0, 12.0])
w.para("Each complete run builds the corpus and IR, runs six analyser configurations, and "
       "boots the VM three times: the baseline run (exhaustive and random fault injection for "
       "the dynamic-only baselines), the mapping run (KernelLeakGuard's module-filtered "
       "fault-point sweep) and the confirmation run. Metrics are computed per allocation site: "
       "an approach reports a site when it reports at least one leak allocated there. The "
       "approach 'KernelLeakGuard (complete)' is the tool's full output: confirmed static "
       "warnings plus leaks exposed by its own mapping sweep; its cost counts every execution "
       "of the mapping and confirmation runs.")
w.h2("4.2 Results")
rows = []
order = ["static/naive", "static/full", "hybrid", "klg/combined", "dynamic/exhaustive",
         "dynamic/random"]
names = {"static/naive": "Static, naive", "static/full": "Static, KernelLeakGuard",
         "hybrid": "Hybrid (confirmed warnings)", "klg/combined": "KernelLeakGuard (complete)",
         "dynamic/exhaustive": "Dynamic, exhaustive FI",
         "dynamic/random": "Dynamic, random FI", "cppcheck": "cppcheck 2.19"}
for n in order + (["cppcheck"] if "cppcheck" in A else []):
    if n in A:
        a = A[n]
        rows.append([names[n], a["tp"], a["fp"], a["fn"], f"{a['precision']:.2f}",
                     f"{a['recall']:.2f}", f"{a['f1']:.2f}"])
t_main = w.next_table()
w.para(f"{t_main} summarises detection quality; {w.next_figure()} plots precision and recall.")
w.table(["Approach", "TP", "FP", "FN", "Precision", "Recall", "F1"], rows,
        "Detection results on the benchmark (per allocation site)", widths=[5, 1.3, 1.3, 1.3, 2.3, 2.3, 2])
w.figure(FIG / "fig_precision_recall.png", "Precision and recall per approach", 15.5)
w.para(
    f"The static analyser reports {n_warn} warnings on {m('static/full', 'tp') + m('static/full', 'fp')} "
    f"allocation sites, finding {m('static/full', 'tp')} of the {GT['leak_sites']} leaking sites "
    f"with {m('static/full', 'fp')} false alarm. The naive analysis that only looks for a "
    f"missing kfree() finds the same leaks but raises {m('static/naive', 'fp')} false alarms, "
    "most of them ownership transfers (list insertion, caller-owned structures, RCU and kref "
    "release, factories). Runtime verification confirmed "
    f"{n_conf} warnings with kmemleak evidence, refuted {n_ref} and left {n_inc} "
    f"inconclusive; the hybrid approach therefore reaches precision "
    f"{m('hybrid', 'precision'):.2f}: every reported leak is backed by a reproduction. "
    f"The mapping sweep additionally exposed "
    f"{', '.join(A['klg/combined'].get('from_sweep_only', [])) or 'no further leaks'}, "
    f"which the static analysis misses by design (Section {SEC_AN}), so the complete tool finds "
    f"{m('klg/combined', 'tp')} leaks. cppcheck, a widely used C static analyser given a "
    f"model of kmalloc/kfree, finds {m('cppcheck', 'tp')} with {m('cppcheck', 'fp')} false "
    f"alarm(s): kernel-specific patterns such as error codes from other calls, copy_from_user "
    f"failures, wrappers and slab caches are outside its model.")
fig_tri = w.next_figure()
w.figure(FIG / "fig_triage.png", "Runtime verdicts for the static warnings", 12)
tri = ev.get("triage", {})
w.para(f"{fig_tri} shows what happened to each warning. All confirmed warnings are real leaks. "
       "The static false positive on klg_s09 (a correct rollback loop that the path search "
       "cannot prove safe because it does not reason about the loop counter) was refuted: the "
       "predicted allocation failures were injected and kmemleak found nothing.")
w.h3("4.2.1 Ablation study")
w.figure(FIG / "fig_ablation.png", "F1 score with each analysis refinement disabled", 15)
w.figure(FIG / "fig_static_breakdown.png", "True and false static reports per configuration", 15)
abl = []
for n, label in (("static/naive", "all refinements off"), ("static/no-escape", "no ownership transfer"),
                 ("static/no-interproc", "no function summaries"), ("static/no-containers", "no stack objects"),
                 ("static/no-corr", "no branch correlation"), ("static/full", "full analysis")):
    a = A[n]
    abl.append([label, a["tp"], a["fp"], a["fn"], f"{a['precision']:.2f}", f"{a['recall']:.2f}",
                f"{a['f1']:.2f}", f"{a['analysis_ms']:.0f}"])
w.table(["Configuration", "TP", "FP", "FN", "Precision", "Recall", "F1", "Time (ms)"], abl,
        "Ablation of the static analyser", widths=[4.4, 1.1, 1.1, 1.1, 2, 1.7, 1.4, 2.2])
w.para(
    "Each refinement matters. Without ownership-transfer analysis precision drops to "
    f"{m('static/no-escape', 'precision'):.2f}, because objects handed to lists, callers or "
    "release callbacks look leaked. Without function summaries the analyser misses leaks "
    "through allocation and release wrappers and treats every module call as capturing "
    f"(recall {m('static/no-interproc', 'recall'):.2f}). Without stack-object tracking, "
    "pointers kept in local arrays and structures are treated as escaped "
    f"(recall {m('static/no-containers', 'recall'):.2f}). Branch correlation removes the "
    "infeasible path in klg_s10, where allocation and release are guarded by the same "
    "condition.")
w.h3("4.2.2 Case study: a confirmed leak")
case = next((c for r in static.values() for c in r["candidates"] if c["module"] == "klg_l02_goto_ladder"), None)
if case:
    v = next(x for x in ver["verdicts"] if x["id"] == case["id"])
    src = (ROOT / "corpus" / "klg_l02_goto_ladder.c").read_text().splitlines()
    lo, hi = case["alloc"]["line"] - 4, case["exit"]["line"] + 6
    w.para("klg_l02 jumps to the wrong cleanup label when kasprintf() fails, skipping the release "
           "of the transmit buffer:")
    w.code("\n".join(f"{i:3d}  {src[i - 1]}" for i in range(lo, min(hi, len(src)) + 1)))
    t0 = v["tests"][0] if v["tests"] else {}
    w.para(
        f"The analyser reports: memory from {case['allocator']}() at line {case['alloc']['line']} "
        f"in {case['function']}() is not released when the function returns "
        f"{case['return_value']} at line {case['exit']['line']}; trigger: "
        f"{', '.join(t['callee'] + ' (line ' + str(t['line']) + ')' for t in case['triggers'])}; "
        f"confidence {case['confidence']}. During the sweep, fault number {t0.get('fail_nth')} "
        f"failed the call at {t0.get('expected_frame')}. In the confirmation run that fault "
        f"was injected {t0.get('fault_hits')} times and kmemleak reported "
        f"{len(t0.get('leaks', []))} unreferenced objects allocated at line "
        f"{case['alloc']['line']}:")
    if t0.get("leaks"):
        lk = t0["leaks"][0]
        w.code(f"unreferenced object (size {lk['size']}):\n  backtrace:\n    " +
               "\n    ".join(lk["backtrace"]))
    w.para(f"Verdict: **{v['status']}** ({v['reason']}). Suggested fix: jump to err_tx instead "
           "of err_rx.")
w.h3("4.2.3 Test cases and results")
w.para("Each benchmark module is a system-level test case: the expected outcome comes from the "
       "ground-truth annotations, and the test passes when the static result and the runtime "
       "verdict agree with it. A leaky module passes when its leak is reported and confirmed; "
       "a safe module passes when no leak is confirmed.")
gt_sites = {}
for src in corpus_sources():
    for no, line in enumerate(src.read_text().splitlines(), 1):
        mm = re.search(r"GT:(LEAK|SAFE)", line)
        if mm:
            gt_sites[(src.stem, no)] = mm.group(1)
vmap = {v["id"]: v for v in ver["verdicts"]}
cases, passed = [], 0
for i, src in enumerate(corpus_sources(), 1):
    mod = src.stem
    leak_lines = sorted(l for (m_, l), lab in gt_sites.items() if m_ == mod and lab == "LEAK")
    cands = static.get(mod, {}).get("candidates", [])
    flagged = sorted({c["alloc"]["line"] for c in cands})
    conf = sorted({c["alloc"]["line"] for c in cands if vmap.get(c["id"], {}).get("status") == "confirmed"})
    expected = f"leak at {', '.join(map(str, leak_lines))}" if leak_lines else "no leak"
    st_txt = f"flagged {', '.join(map(str, flagged))}" if flagged else "no warning"
    statuses = sorted({vmap[c["id"]]["status"] for c in cands if c["id"] in vmap})
    rt_txt = ", ".join(statuses) if statuses else "—"
    ok = (set(leak_lines) <= set(conf)) if leak_lines else not conf
    passed += ok
    cases.append([f"TC{i:02d}", mod.replace("klg_", ""), expected, st_txt, rt_txt,
                  "Pass" if ok else "Fail"])
w.table(["ID", "Module", "Expected", "Static", "Runtime verdict(s)", "Result"], cases,
        "System test cases (one per benchmark module)", widths=[1.2, 3.8, 2.6, 2.6, 4.2, 1.4], size=8.5)
fails = [c for c in cases if c[-1] == "Fail"]
w.para(f"{passed} of {len(cases)} system test cases pass. The failing cases are the known "
       f"limitations discussed in Section {SEC_AN}: "
       + "; ".join(f"{c[1]} ({c[4] if c[4] != '—' else 'not reported'})" for c in fails) + ".")
tr = RES / "test_results.txt"
if tr.exists():
    lines = tr.read_text().splitlines()
    unit = []
    for i, l in enumerate(lines):
        if " ... " not in l or not l.startswith("test_"):
            continue
        name, rest = l.split(" ... ", 1)
        status = rest.strip().split()[-1] if rest.strip() else ""
        if status not in ("ok", "FAIL", "ERROR"):
            # Library warnings printed after "..." push the result onto a later line.
            status = next((x.strip() for x in lines[i + 1:] if x.strip() in ("ok", "FAIL", "ERROR")),
                          "?")
        unit.append(f"{name} ... {status}")
    w.para(f"In addition, {len(unit)} automated unit and regression tests (tests/test_klg.py) "
           "check log parsing, kmemleak parsing, size matching, fault-point matching, test "
           "scheduling, ground-truth parsing and the analyser's behaviour on individual "
           "modules (including each ablation option):")
    w.table(["Test", "Result"],
            [[re.sub(r" \(.*\)", "", l.split(" ... ")[0]).replace("test_", "").replace("_", " "),
              l.split(" ... ")[1].upper()] for l in unit],
            "Unit and regression tests", widths=[12, 4], size=9)
if fixes:
    w.h3("4.2.4 Fix patches")
    w.para(
        "For every confirmed leak KernelLeakGuard generates a patch: it inserts the release "
        "statement the function already uses for the object on another path (or the "
        "deallocator matching the allocator) at the start of the error branch, only when that "
        "branch is reached exclusively from the failing call; leaks of allocations made in a "
        "loop receive a rollback loop. Each patch is validated three ways: the patched module "
        "compiles, klg-analyze no longer reports the leak, and in the VM a module-filtered "
        "sweep exercises every fault point of the patched module with kmemleak and SLUB "
        "debugging (slub_debug=FZPU, which detects double frees and memory corruption) active. "
        f"{n_fix_ok} of {n_fix} patches pass all three checks. "
        + (f"The remaining {n_fix_rt} patch(es) (the loop rollback for klg_l04) removes the "
           "leak at runtime, with every fault point of the module exercised, but the analyser "
           "still reports the site because it cannot reason about the loop counter — the same "
           "limitation as the klg_s09 warning."
           if n_fix_rt else ""))
    w.table(["Module", "Release inserted", "Compiles", "Static clean", "Faults exercised",
             "Runtime clean", "Status"],
            [[f["module"].replace("klg_", ""),
              re.sub(r"; validation failed", "", f.get("reason", "")),
              "yes" if f["checks"].get("compiles") else "no",
              "yes" if f["checks"].get("static_clean") else "no",
              f["checks"].get("runtime_faults_exercised", "—"),
              "yes" if f["checks"].get("runtime_clean") else "no",
              f["status"]] for f in fix_main],
            "Generated fix patches and their validation", widths=[3.2, 5.6, 1.5, 1.6, 1.7, 1.6, 1.8],
            size=8)
    ex = next((f for f in fix_main if f["module"] == "klg_l02_goto_ladder" and f.get("patch")), None)
    if ex:
        w.para("Example: the generated patch for klg_l02.")
        w.code(ex["patch"], size=8)
w.h2("4.3 Performance Metrics")
w.figure(FIG / "fig_cost.png", "Executions of kernel routines needed for verification", 12)
w.table(["Metric", "Value"], [
    ["Functions analysed / allocation sites", f"{funcs_total} / {sites_total}"],
    ["Static analysis time, all 32 modules", f"{an_ms:.0f} ms ({an_ms / GT['modules']:.1f} ms per module)"],
    ["Mapping VM run (module-filtered fault-point sweep)", f"{vm_map:.0f} s"],
    ["Confirmation VM run", f"{vm_conf:.0f} s"],
    ["Baseline VM run (exhaustive + random fault injection)", f"{vm_sweep:.0f} s"],
    ["kmemleak rounds in confirmation", f"{ver['kmemleak_rounds']}"],
    ["Executions: KernelLeakGuard (sweep + confirmation)",
     f"{m('hybrid', 'executions')} ({A['hybrid'].get('mapping_executions')} + "
     f"{A['hybrid'].get('confirm_executions')})"],
    ["Executions: exhaustive fault injection", f"{m('dynamic/exhaustive', 'executions')}"],
    ["Executions: random fault injection", f"{m('dynamic/random', 'executions')}"],
], "Performance of the pipeline", widths=[9, 7])
if run_evs:
    rr = []
    for i, e in enumerate(run_evs, 1):
        h, kc, ex, rd = (e["approaches"][k] for k in ("hybrid", "klg/combined",
                                                       "dynamic/exhaustive", "dynamic/random"))
        rr.append([f"Run {i}", f"{h['tp']} / {h['fp']} / {h['fn']}", f"{kc['tp']} / {kc['fp']} / {kc['fn']}",
                   f"{ex['tp']} / {ex['fp']} / {ex['fn']}", f"{rd['tp']} / {rd['fp']} / {rd['fn']}"])
    hy_tp = [e["approaches"]["hybrid"]["tp"] for e in run_evs]
    hy_fp = [e["approaches"]["hybrid"]["fp"] for e in run_evs]
    same = len(set(hy_tp)) == 1
    w.para(f"The complete pipeline was run {len(run_evs)} times from scratch (new VM boots, "
           "new fault-point sweeps); the main results above are those of the last run. "
           + ("The hybrid verdicts are identical in every run. " if same else
              f"The hybrid confirmed between {min(hy_tp)} and {max(hy_tp)} leaks with "
              f"{max(hy_fp)} false positives in every run. The variation comes from the vmalloc "
              "leak in klg_l10: kmemleak tracks a vmalloc area with a minimum reference count of "
              "two (the kernel's own vm_struct legitimately points to it), so a single extra "
              "stale copy of its address hides the leak in that scan. ")
           + "The dynamic baselines vary for the same reason and because random injection does "
           "not reach the same fault points every time. A false positive never occurred.")
    w.table(["Run", "Hybrid TP / FP / FN", "KLG complete TP / FP / FN", "Exhaustive TP / FP / FN",
             "Random TP / FP / FN"], rr,
            "Results across independent runs (fresh VM boots)", widths=[2, 3.6, 3, 3.8, 3.6])
REAL = RES / "real"
real_sum = json.loads((REAL / "summary.json").read_text()) if (REAL / "summary.json").exists() else None
if real_sum and real_sum.get("runtime_modules"):
    rver = json.loads((REAL / "runtime" / "verification.json").read_text())
    rtri = json.loads((REAL / "triage.json").read_text()) if (REAL / "triage.json").exists() else []
    rstat = {p.stem: json.loads(p.read_text()) for p in sorted((REAL / "static" / "full").glob("*.json"))}
    rmods = real_sum["runtime_modules"]
    w.h2("4.4 Evaluation on Real Kernel Code")
    w.para(
        f"To check the approach beyond our own benchmark, KernelLeakGuard was run on "
        f"{real_sum['modules']} real modules of Linux 6.18.55 that initialise without hardware "
        "(virtual network devices, block and SCSI simulators, device-mapper targets, file "
        "systems, sound and input drivers; vm/real_modules.fragment). Each module's IR is built "
        "from all of its C files with the exact kbuild flags and linked with llvm-link; "
        f"dependencies ({', '.join(real_sum.get('preloaded_dependencies', [])) or 'none'}) are "
        f"loaded first. The static analysis covered {real_sum['functions']} functions with "
        f"{real_sum['alloc_sites']} allocation sites and reported {real_sum['warnings']} "
        f"warnings in {real_sum['analysis_ms'] / 1000:.1f} s.")
    _hist = json.loads((RES / "real" / "precision_history.json").read_text())["steps"]
    w.para(
        "Real code exposed false-positive patterns that are absent from the benchmark, and each "
        "was fixed in the analyser by a general rule, not by naming kernel functions. (1) Kernel "
        "lookup and factory helpers return an ERR_PTR error code (checked with IS_ERR()) instead "
        "of NULL; the IS_ERR() edge is now pruned like the NULL edge. (2) Helpers such as "
        "hfs_bnode_find(), find_build_dev_info() or add_fsync_inode() link the new object into "
        "a hash table or list before returning it, so the caller does not own it; such helpers "
        "are now lookups, not allocators. (3) clang emits a cleanup-destination switch when a "
        "goto leaves a scoped block; its default edge cannot execute, but the path search "
        "followed it and reached the return without the cleanup. Conditions are now evaluated "
        "on the values their operands have along the path, which also handles error codes kept "
        "in a variable (snd_aloop's err < 0 at a shared unlock label). Investigating a missed seeded leak (Section 4.5) also uncovered a "
        "false negative: a single return of phi(object, NULL) was treated as returning the "
        "object on every path, hiding leaks on the NULL-returning error path. The table shows "
        "the warnings after each step; no step changed any benchmark result in any of the six "
        "analyser variants, and every warning removed by the ownership rule was checked by hand "
        "in the kernel source.")
    w.table(["Analyser refinement", "Static warnings (39 modules)"],
            [[h["step"], h["warnings"]] for h in _hist],
            "Effect of each precision refinement on real kernel code", widths=[10.5, 4], size=9)
    w.para(
        (f"The runtime stage was run on all {len(rmods)} modules "
         if len(rmods) == real_sum["modules"] else
         f"The runtime stage was run on {len(rmods)} representative modules ")
        + f"({', '.join(rmods)}). Hardware virtualization was unavailable in WSL during this "
        "run (Windows virtualization-based security), so the guest ran under QEMU software "
        "emulation, which is correct but 10-20x slower. For each module the mapping run failed "
        "every fault point of its initialisation reachable from the module's own code (library "
        "modules without an initialisation routine have none), with kmemleak checked after each "
        "module, and every static warning was given a targeted confirmation test.")
    rows = []
    crashes_by = {}
    for run_ in rver.get("crashes", {}).values():
        for cr in run_:
            log = cr.get("where", {}).get("log", "")
            if log.startswith("sweep_"):
                crashes_by.setdefault(log[len("sweep_"):], []).append(cr)
    for mname in rmods:
        st = rstat.get(mname, {}).get("stats", {})
        verds = [v for v in rver.get("verdicts", []) if v["module"] == mname]
        vc = {}
        for v in verds:
            vc[v["status"]] = vc.get(v["status"], 0) + 1
        rows.append([mname, st.get("functions", 0), st.get("alloc_sites", 0),
                     len(rstat.get(mname, {}).get("candidates", [])),
                     len(rver.get("fault_points", {}).get(mname, [])),
                     ", ".join(f"{n} {k}" for k, n in sorted(vc.items())) or "—",
                     len(crashes_by.get(mname, []))])
    w.table(["Module", "Functions", "Alloc. sites", "Warnings", "Faults injected",
             "Runtime verdicts", "Guest crashes"], rows,
            "Real kernel modules run in the VM", widths=[3, 1.8, 1.8, 1.8, 2, 4, 1.8], size=8.5)
    tc = {}
    for t in rtri:
        tc[t["label"]] = tc.get(t["label"], 0) + 1
    reviewed = [t for t in rtri if t["basis"] == "reviewed in source"]
    w.para(
        f"**Manual review.** Of the {len(rtri)} warning(s) in these modules, "
        + ", ".join(f"{n} {'is a' if n == 1 else 'are'} {k}{'' if n == 1 else 's'}"
                    for k, n in sorted(tc.items()))
        + f"; all {len(reviewed)} were read in the kernel source, and the real bugs are "
        "described below. The false positives share causes the analyser does not model: release "
        "decisions on values held in memory (in->index, *raw_super), on pointer identity "
        "(free new unless e == new, name != s_name_buf), on the relation between two loop "
        "counters, and ownership handed to asynchronous work. Before the refinements above, "
        "the same review had found every high-confidence warning to be a false positive, which "
        "is what motivated them. No warning was confirmed at runtime, so none became a false "
        "report; the two real bugs lie in mount-time code that module initialisation does not "
        "reach.")
    rv = {}
    for v in rver.get("verdicts", []):
        rv[v["status"]] = rv.get(v["status"], 0) + 1
    unreach = sum(1 for v in rver.get("verdicts", [])
                  if v["status"] == "inconclusive" and v["reason"].startswith("no fault point"))
    w.para(
        f"**Runtime verdicts.** Of the {sum(rv.values())} warnings, "
        + ", ".join(f"{n} were {k}" for k, n in sorted(rv.items()))
        + f". {unreach} inconclusive verdicts mean that no fault point of module initialisation "
        "reaches the warning's failing call: the code runs only on other entry points (file "
        "system mount, ioctl, netlink, block I/O), which the runtime stage does not drive yet. "
        "Driving those entry points (for example with mount images or syzkaller-style system "
        "call programs) is the main extension needed for real code.")
    leaks = rver.get("sweep_leaks", [])
    w.para(
        f"**Leaks found by the sweep.** Exercising {real_sum['fault_points']} fault points "
        f"of module initialisation left "
        + (f"{len(leaks)} unreferenced allocation site(s): "
           + "; ".join(f"{l['module']} {l['file']}:{l['line']} ({l['objects']} objects)" for l in leaks)
           if leaks else "no unreferenced object in any of these modules: every injected failure "
           "in their initialisation released its memory correctly")
        + ".")
    _rc_file = RES / "real" / "root_causes.json"
    rc = json.loads(_rc_file.read_text()) if _rc_file.exists() else {}
    sl = rc.get("slub_sysfs_leak")
    if sl and any(l["module"] == "erofs" for l in leaks):
        w.para(
            "**Root cause of the erofs report: a leak in the SLUB allocator.** The unreferenced "
            "objects are complete slab caches (a struct kmem_cache, its per-node structures and "
            "its kstrdup'd name, e.g. \"erofs_pcluster-1\"). We bisected erofs's initialisation "
            "with the fault-probe helper (one kmemleak scan per batch of fault points, then per "
            f"fault point): {sl['stock']['leaking_batches']} of {sl['stock']['batches']} batches "
            f"leaked, and the trigger is {sl['trigger']}. The mechanism, confirmed with the full "
            "kernel log in the guest, is: "
            + "; ".join(sl["mechanism"]) + ". The kernel's own warning at destruction time shows "
            "the path:")
        w.code("kobject: '(null)': is not initialized, yet kobject_put() is being called.\n"
               + "\n".join("  " + t for t in sl["warn_trace"])
               + "\nrefcount_t: underflow; use-after-free.", size=8)
        w.para(
            "erofs is only the messenger: any kernel code that creates a mergeable slab cache can "
            "leak it this way under allocation failure, and the sweep of all modules indeed "
            f"reported the same leak in {', '.join(sl.get('also_in', [])[:-1])} and "
            f"{sl.get('also_in', [''])[-1]}. The code is "
            f"{sl['upstream']}. Our fix "
            f"({sl['patch']}) makes sysfs_slab_release() release a cache whose kobject was never "
            "initialised directly instead of calling kobject_put(). Re-running the same "
            f"{sl['patched']['batches']} batches on a guest kernel built with the patch exercised "
            f"the failing sysfs registration {sl['patched']['sysfs_failures_exercised']} times "
            f"and left {sl['patched']['unreferenced']} unreferenced objects and "
            f"{sl['patched']['kobject_warnings']} kobject warnings (stock kernel: "
            f"{sl['stock']['unreferenced']} objects). The fix is validated in the VM but has "
            "not been submitted upstream; the mailing lists should be searched for a pending "
            "fix before it is.")
    ff = rc.get("f2fs_sysfs_leak")
    if ff:
        ib = ff["introduced_by"]
        st, pt = ff["stock_leaked_names"], ff["patched_leaked_names"]
        w.para(
            "**A regression in f2fs found by the sweep.** The other leak reported by the sweep is "
            "in f2fs: " + "; ".join(ff["mechanism"]) + f". The code was introduced in "
            f"{ib['date'][:7]} by commit {ib['commit']} (\"{ib['subject']}\"): {ib['note']}; it "
            f"is {ff['upstream']}. Our patch ({ff['patch']}) puts each kobject from its own "
            "failure path and still never puts the uninitialised one. On the "
            f"{ff['trigger'].split(':')[0]} the stock module leaked "
            + ", ".join(f"{n} \"{k}\" names" for k, n in sorted(st.items()))
            + f" and the patched module {sum(pt.values())}. The leaked names are allocated inside "
            "the kobject core, outside the module, so only the runtime stage can find this kind "
            "of leak.")
    nt = rc.get("ntfs3_do_action_leak")
    if nt:
        v = nt["validation"]
        w.para(
            "**A leak found statically in ntfs3.** Of the remaining static warnings, the "
            "high-confidence one in ntfs3's log replay is a genuine leak: "
            + "; ".join(nt["mechanism"]) + f". The code is {nt['upstream']}. Our fix "
            f"({nt['patch']}) calls mi_put(mi) before returning; built against the guest kernel "
            f"it compiles, and re-analysing the patched module removes exactly this warning "
            f"({v['warnings_original']} warnings before, {v['warnings_patched']} after, none new). "
            f"It is {nt['runtime']}, so we report it as a source-confirmed static finding.")
    uf = rc.get("ufs_bforget_leak")
    if uf:
        v = uf["validation"]
        w.para(
            "**A known but unfixed leak in ufs.** The second real bug among the static warnings: "
            + "; ".join(uf["mechanism"]) + f". The code is {uf['upstream']}, so KernelLeakGuard "
            "independently rediscovered it. Our patch "
            f"({uf['patch']}) adds the kfree(); it compiles and re-analysis removes exactly this "
            f"warning ({v['warnings_original']} warnings before, {v['warnings_patched']} after, "
            f"none new). It is {uf['runtime']}.")
    nb = rc.get("null_blk_crash")
    if crashes_by:
        def _kinds(v):
            k = {}
            for c_ in v:
                k[c_["kind"]] = k.get(c_["kind"], 0) + 1
            return ", ".join(f"{n} {kind}{'es' if kind == 'crash' and n != 1 else 's' if n != 1 else ''}"
                             for kind, n in sorted(k.items()))
        crash_mods = {m_: v for m_, v in crashes_by.items() if any(c_["kind"] == "crash" for c_ in v)}
        hang_mods = [m_ for m_, v in crashes_by.items() if all(c_["kind"] == "hang" for c_ in v)]
        first_mod, crs = next(iter(crash_mods.items())) if crash_mods else next(iter(crashes_by.items()))
        trace = [l for l in crs[0]["console"] if re.search(r"BUG|Oops|RIP|\+0x", l)][:9]
        w.para(
            "**Kernel crashes and hangs found.** During the sweep the guest had "
            + "; ".join(f"{_kinds(v)} while loading {k}" for k, v in crashes_by.items())
            + f". Every {first_mod} crash is the same page fault in bdev_release() reading freed "
            "module memory (below); the crash-recovery mechanism resumed the sweep after each one "
            "and stopped the module's sweep after repeated crashes."
            + (f" The {', '.join(hang_mods)} hangs (no progress for 15 minutes at certain fault "
               "points of its initialisation) were not analysed; to save time under software "
               "emulation its sweep was stopped after these hangs instead of the usual ten."
               if hang_mods else ""))
        w.code("\n".join(trace), size=8)
        if nb:
            w.para(
                f"**Root cause of the null_blk crash.** Probing fault points "
                f"{nb['probed'][0]}-{nb['probed'][-1]} one at a time on a freshly booted guest "
                f"crashed it at {', '.join(map(str, nb['crashed']))}, so no earlier state is "
                f"needed. With a verbose console the trigger is {nb['trigger']}. The mechanism: "
                + "; ".join(nb["mechanism"]) + ". The crash stack confirms the deferred release ("
                + " <- ".join(nb["crash_stack"]) + "). Any module that adds a disk and then "
                f"fails its initialisation is exposed; the code is {nb['upstream']}. We did not "
                f"validate a fix: {nb['fix']}.")
if seeds:
    w.h2(f"{SEC_SEED} Seeded Leaks in Real Kernel Code")
    w.para(
        "The current real modules contain few early-exit leaks on code the runtime stage can "
        "execute, so to evaluate the complete detect-confirm-fix loop on real kernel code we "
        "re-introduce leaks into real kernel sources and build the module out of tree against "
        "the guest kernel, unchanged apart from that change. Where possible the leak is a real "
        "historical bug: the release added by an upstream leak fix is removed again, so the code "
        "is exactly what Linux shipped before that fix and the fix is the upstream patch. "
        "Otherwise one release statement is removed as a careless patch would; such bugs are "
        "ours and clearly marked. A warning "
        "counts as detected only if it is new compared with the unmodified module, and the fix "
        "(re-inserting the statement) must compile, clear the warning and leave kmemleak clean "
        "on a VM re-run.")
    srows = []
    for s_ in seeds:
        w0 = s_["warnings"][0] if s_["warnings"] else {}
        h = s_.get("history")
        srows.append([s_["module"], s_["file"].split("/")[-1] + ":" + str(s_["removed_line"]),
                      s_["removed"],
                      f"real bug (fixed by {h['commit']}, {h['date'][:4]})" if h else "seeded by us",
                      "yes" if s_["detected"] else "no",
                      "yes" if s_.get("confirmed") else "no",
                      "yes" if s_.get("fixed") else "no"])
    w.table(["Module", "Removed at", "Removed statement", "Origin", "Detected", "Confirmed (VM)",
             "Fixed"], srows, "Early-exit leaks re-introduced into real kernel modules",
            widths=[1.8, 2.4, 3.2, 3.2, 1.4, 1.7, 1.1], size=8)
    for s_ in seeds:
        h = s_.get("history")
        w.para(f"**{s_['module']}, {s_['function']}()"
               + (f" — upstream commit {h['commit']} \"{h['subject']}\" ({h['date']})" if h else "")
               + f".** {s_['bug']} {s_.get('reachable', '')}")
        w0 = s_["warnings"][0] if s_["warnings"] else None
        if w0:
            w.para(
                f"KernelLeakGuard reported the allocation at line {w0['alloc']} ({w0['allocator']}) "
                f"leaking at the exit on line {w0['exit']} (returning {w0['return']}, confidence "
                f"{w0['confidence']}); the unmodified module has no such warning.")
        if s_.get("confirmed"):
            ev0 = s_.get("evidence", [{}])[0]
            w.para(
                f"In the guest VM the module-filtered sweep mapped the failing call, and the "
                f"targeted test ({ev0.get('reason', '')}) made module initialisation fail; "
                "kmemleak then reported the object as unreferenced, with the allocation "
                "backtrace pointing back into the module's init path (module frames symbolised "
                "through klg_modwatch):")
            if ev0.get("backtrace"):
                w.code("unreferenced object:\n  " + "\n  ".join(ev0["backtrace"][:8]), size=8)
            w.para(
                "Re-inserting the removed statement (the generated fix) compiles, clears the "
                "static warning and leaves kmemleak with nothing to report on the VM re-run"
                + (f"; the guest did not crash ({s_.get('crashes', 0)} crashes)." if s_.get("crashes") == 0 else "."))
        elif s_.get("vm_note"):
            w.para(s_["vm_note"])
    w.para(
        "**Choosing seeds.** A seed is only useful when kmemleak can observe the leak, which "
        "rules out most candidates, and we report the rejected ones. In brd, removing "
        "brd_free_device() leaves the object linked in the global brd_devices list: it stays "
        "reachable, so this is a stale-entry bug, not an unreferenced leak. The analyser "
        "initially flagged it, and its ownership rule (Section 4.4) now correctly treats "
        "brd_find_or_alloc_device() as a lookup. In zram (zram_add()) and scsi_debug the object "
        "is first stored in an IDR or passed to a registering helper, so the analyser "
        "conservatively treats it as escaped and does not warn: these are honest misses of the "
        "escape analysis on code where ownership is handed over and then taken back. A "
        "historical scsi_debug fix (e6d773f93a49, a device name leaked when device_register() "
        "fails) was not used because the leaked name is allocated inside the driver core, "
        "outside the module the static stage analyses. The "
        "null_blk seed also revealed two analyser gaps, both fixed generally: the phi-return "
        "false negative (Section 4.4) and the missing model of badblocks_init(), which only "
        "initialises the struct badblocks it is given.")
w.h2(f"{SEC_AN} Analysis")
w.para(
    "**Static versus hybrid.** Runtime verification removed all static false positives "
    f"({fp_removed} in this run) and attached reproduction steps and kmemleak backtraces to "
    "every confirmed report. The cost is a modest loss of recall: warnings whose failure "
    "cannot be injected stay inconclusive rather than confirmed. In the corpus this "
    "happens for klg_l15, where ida_alloc() never allocates for small identifiers (they are "
    "stored inline in the XArray), so its failure cannot be provoked; reporting it as "
    "inconclusive is the honest outcome, and the warning is still shown to the developer.")
w.para(
    "**Hybrid versus dynamic-only.** Exhaustive fault injection runs every routine once per "
    f"fault point ({m('dynamic/exhaustive', 'executions')} executions, dominated by module "
    "loading, which has hundreds of fault points) and random injection uses a fixed budget. "
    "KernelLeakGuard restricts its sweep with the kernel's fault-injection stack-trace filter "
    "(require-start/require-end set to the module's code, taken from klg_modwatch's log), so "
    "fail-nth counts only fault points reached from the module itself; together with the "
    f"targeted confirmation it needs {m('hybrid', 'executions')} executions in total and "
    f"finds {m('klg/combined', 'tp')} leaks, against {m('dynamic/exhaustive', 'tp')} for the "
    "exhaustive baseline. Leaks in module initialisation code are reported by kmemleak with raw "
    "addresses because the module is unloaded after its failed initialisation; klg_modwatch, "
    "a helper module that logs each module's load address and symbols, turns them back into "
    "exact source lines. Dynamic tools report only a backtrace, whereas KernelLeakGuard's "
    "report names the leaking exit, the returned error, the failing call and a validated fix.")
w.para(
    "**Trustworthy kmemleak results.** kmemleak decides that an object is referenced if any "
    "scanned memory contains a value equal to its address, so a stale copy of a pointer hides "
    "a real leak. During development the leak in klg_l17 (a pointer kept in a local structure) "
    "was confirmed in some runs and missed in others. We traced two sources of stale copies: "
    "reused kernel stacks, and reused slab objects that still contained an old SLUB freelist "
    "link pointing to the leaked buffer (kmalloc does not clear memory). The guest therefore "
    "allocates thread stacks from the page allocator, erases kernel stacks on return to user "
    "space, disables kmemleak's task-stack scanning (all tested routines have returned before a "
    "scan) and boots with init_on_alloc=1 init_on_free=1 so that slab memory is zeroed. This "
    "made the klg_l17 verdict stable. vmalloc'd memory remains less stable (see the repeated "
    "runs in Section 4.3): such leaks can still be hidden in an individual scan, which is why "
    "a missing confirmation is reported as 'not reproduced', never as 'safe'.")
w.para(
    "**Limitations.** The analyser does not track ownership through fields of other heap "
    "objects, so the nested-buffer leak in klg_l16 is missed by design; field-sensitive heap "
    "ownership (as in K-MELD) is future work. Path-insensitivity on loop counters causes the "
    "klg_s09 warning, which the runtime stage then refutes. The benchmark is written by us; "
    "results on it demonstrate the mechanism but do not predict performance on the whole "
    "kernel.")
w.para(
    "**Comparison with MLEE.** MLEE analyses the whole kernel and found 120 new leaks; "
    "KernelLeakGuard analyses modules with a smaller MLEE-style analysis. Its contribution is "
    "the verification loop: MLEE's reports require manual confirmation, while KernelLeakGuard "
    "confirms or refutes each warning automatically with kernel evidence.")

# ------------------------------------------------------------ chapter 5 -----
w.chapter_heading(5, "Conclusion and Future Work")
w.h2("5.1 Conclusion")
w.para(
    "KernelLeakGuard detects memory leaks on Linux kernel early-exit paths with an LLVM-based "
    "static analyser and verifies every warning by injecting the predicted failure in a "
    "QEMU/KVM guest and checking kmemleak. The project applies core operating-system concepts "
    "(kernel memory management, error handling, system calls, per-task kernel state, kernel "
    "modules and virtualisation) to a practical systems problem. On a benchmark of "
    f"{GT['modules']} modules the static analyser achieves F1 {m('static/full', 'f1'):.2f} "
    f"against {m('static/naive', 'f1'):.2f} for a naive missing-kfree analysis, and runtime "
    f"verification confirms {n_conf} leaks with kernel evidence, refutes the remaining false "
    f"positive and reaches precision {m('hybrid', 'precision'):.2f}. The complete tool finds "
    f"{m('klg/combined', 'tp')} of {GT['leak_sites']} leaks with no false positive using "
    f"{m('hybrid', 'executions')} executions, compared with "
    f"{m('dynamic/exhaustive', 'tp')} leaks and {m('dynamic/exhaustive', 'executions')} "
    f"executions for exhaustive fault injection, and generates validated fix patches for "
    f"{n_fix_ok} of {n_fix} confirmed leaks.")
if real_sum and real_sum.get("runtime_modules"):
    w.para(
        f"On {real_sum['modules']} real Linux modules the static analyser reported "
        f"{real_sum['warnings']} warnings after general precision refinements (115 before), "
        "and the runtime stage confirmed none of them, so no false report reached the "
        "developer. "
        + (f"{len([s_ for s_ in seeds if s_.get('confirmed')])} of {len(seeds)} leaks "
           "re-introduced into real module code"
           + (", including a real historical bug," if sum(1 for s_ in seeds if s_.get("history")
                                                             and s_.get("confirmed")) == 1
              else ", including real historical bugs," if any(s_.get("history") and s_.get("confirmed")
                                                               for s_ in seeds) else "")
           + " were detected, confirmed in the VM with kmemleak evidence and fixed end to end. "
           if seeds else "")
        + "Exercising the initialisation of "
        "real modules under fault injection also found three kernel defects that we "
        "root-caused and checked against mainline: a slab-cache leak in the SLUB allocator when "
        "sysfs registration fails and a kobject-name leak in f2fs introduced by a 2026 fix (both "
        "fixes validated in the VM), and a use-after-free of module memory when a module's "
        "initialisation fails after it added a disk. The static analyser "
        "also found leaks in ntfs3's log replay and in ufs's truncation that are still present "
        "in mainline; our fixes remove the warnings. The runtime half is therefore useful beyond confirming static "
        "warnings.")
w.para("Key findings: ownership-transfer analysis is the single most important refinement for "
       "precision; predicting the failing call and filtering fault injection to the module's "
       "own code make runtime verification cheaper and more precise than blind fault "
       "injection; and kmemleak evidence is trustworthy only when stale pointer copies on "
       "reused stacks and in reused slab memory are eliminated.")
w.h2("5.2 Future Work")
w.bullets([
    "Field-sensitive heap ownership to detect nested leaks such as klg_l16.",
    "Track error codes stored in variables (value correlation, e.g. err < 0 at a shared "
    "cleanup label) and release through list iteration: remaining false-positive causes on "
    "real kernel code (Section 4.4).",
    "Drive non-initialisation entry points (file-system images to mount, ioctl and netlink "
    "programs, syzkaller-style system-call sequences) so that warnings outside module "
    "initialisation become testable.",
    "Run the runtime stage with hardware acceleration (KVM) instead of software emulation, "
    "which makes the real-module run 10-20x faster and allows repeated runs.",
    "Report the SLUB slab-cache leak, the f2fs regression, the ntfs3 log-replay leak and the "
    "ufs leak upstream with their patches, and the null_blk / block-layer use-after-free to the block maintainers, after "
    "checking the mailing lists for pending fixes; confirm the ntfs3 leak at runtime with a "
    "crafted image.",
    "Reproducing known MLEE-reported leaks on the corresponding historical kernel versions.",
    "Value-range reasoning about loop counters to avoid rollback-loop false positives.",
    "Patches for shared error labels (goto ladders used by several paths), which are "
    "currently left for manual review.",
    "Integration into kernel continuous-integration systems such as KernelCI.",
])
w.para("**Real-world deployment scope.** The command-line tool and dashboard can be run by "
       "driver developers before submitting patches, and the verifier's evidence (failing "
       "call, fault number, kmemleak backtrace) is directly usable in a bug report.")

# ------------------------------------------------------------ references -----
w.chapter_heading(None, "References")
refs = [
    "Wang, Wenwen. “MLEE: Effective Detection of Memory Leaks on Early-Exit Paths in OS Kernels.” "
    "2021 USENIX Annual Technical Conference (USENIX ATC 21), USENIX Association, 2021, "
    "www.usenix.org/conference/atc21/presentation/wang-wenwen.",
    "Saha, Suman, et al. “Hector: Detecting Resource-Release Omission Faults in Error-Handling Code "
    "for Systems Software.” 2013 43rd Annual IEEE/IFIP International Conference on Dependable "
    "Systems and Networks (DSN), IEEE, 2013.",
    "Emamdoost, Navid, et al. “Detecting Kernel Memory Leaks in Specialized Modules with Ownership "
    "Reasoning.” Proceedings of the Network and Distributed System Security Symposium (NDSS), 2021.",
    "Wu, Qiushi, et al. “Understanding and Detecting Disordered Error Handling with Precise Function "
    "Pairing.” 30th USENIX Security Symposium (USENIX Security 21), 2021.",
    "Jiang, Zu-Ming, et al. “Fuzzing Error Handling Code Using Context-Sensitive Software Fault "
    "Injection.” 29th USENIX Security Symposium (USENIX Security 20), 2020.",
    "Lawall, Julia, and Gilles Muller. “Coccinelle: 10 Years of Automated Evolution in the Linux "
    "Kernel.” 2018 USENIX Annual Technical Conference (USENIX ATC 18), 2018.",
    "Palix, Nicolas, et al. “Faults in Linux 2.6.” ACM Transactions on Computer Systems, vol. 32, "
    "no. 2, 2014.",
    "Engler, Dawson, et al. “Bugs as Deviant Behavior: A General Approach to Inferring Errors in "
    "Systems Code.” Proceedings of the 18th ACM Symposium on Operating Systems Principles (SOSP), 2001.",
    "Xie, Yichen, and Alex Aiken. “Context- and Path-Sensitive Memory Leak Detection.” Proceedings "
    "of ESEC/FSE 2005, ACM, 2005.",
    "Cherem, Sigmund, Lonnie Princehouse, and Radu Rugina. “Practical Memory Leak Detection Using "
    "Guarded Value-Flow Analysis.” Proceedings of the ACM SIGPLAN Conference on Programming Language "
    "Design and Implementation (PLDI), 2007.",
    "Sui, Yulei, Ding Ye, and Jingling Xue. “Static Memory Leak Detection Using Full-Sparse Value-Flow "
    "Analysis.” Proceedings of the International Symposium on Software Testing and Analysis "
    "(ISSTA), ACM, 2012.",
    "Rubio-González, Cindy, et al. “Error Propagation Analysis for File Systems.” Proceedings of the "
    "ACM SIGPLAN Conference on Programming Language Design and Implementation (PLDI), 2009.",
    "Lattner, Chris, and Vikram Adve. “LLVM: A Compilation Framework for Lifelong Program Analysis & "
    "Transformation.” International Symposium on Code Generation and Optimization (CGO), IEEE, 2004.",
    "Nethercote, Nicholas, and Julian Seward. “Valgrind: A Framework for Heavyweight Dynamic Binary "
    "Instrumentation.” Proceedings of the ACM SIGPLAN Conference on Programming Language Design and "
    "Implementation (PLDI), 2007.",
    "Serebryany, Konstantin, et al. “AddressSanitizer: A Fast Address Sanity Checker.” 2012 USENIX "
    "Annual Technical Conference (USENIX ATC 12), 2012.",
    "Bellard, Fabrice. “QEMU, a Fast and Portable Dynamic Translator.” Proceedings of the USENIX "
    "Annual Technical Conference, FREENIX Track, 2005.",
    "Bonwick, Jeff. “The Slab Allocator: An Object-Caching Kernel Memory Allocator.” Proceedings of "
    "the USENIX Summer 1994 Technical Conference, 1994.",
    "Google. “syzkaller: An Unsupervised Coverage-Guided Kernel Fuzzer.” GitHub, "
    "github.com/google/syzkaller. Accessed 12 Oct. 2026.",
    "The Linux Kernel Documentation. “Kernel Memory Leak Detector.” kernel.org, "
    "docs.kernel.org/dev-tools/kmemleak.html. Accessed 12 Oct. 2026.",
    "The Linux Kernel Documentation. “Fault Injection Capabilities Infrastructure.” kernel.org, "
    "docs.kernel.org/fault-injection/fault-injection.html. Accessed 12 Oct. 2026.",
    "Love, Robert. Linux Kernel Development. 3rd ed., Addison-Wesley, 2010.",
    "Silberschatz, Abraham, Peter B. Galvin, and Greg Gagne. Operating System Concepts. 10th ed., "
    "Wiley, 2018.",
    "Marjamäki, Daniel. “Cppcheck: A Tool for Static C/C++ Code Analysis.” cppcheck.sourceforge.io. "
    "Accessed 13 Oct. 2026.",
]
for r in refs:
    p = w.para(r, align=WD_ALIGN_PARAGRAPH.LEFT)
    p.paragraph_format.left_indent = R.Cm(1.27)
    p.paragraph_format.first_line_indent = R.Cm(-1.27)

# ------------------------------------------------------------ appendix -----
w.chapter_heading(None, "Appendix: Source Code")
w.chapter = "A"
w.para("The complete source code is in the project repository (KernelLeakGuard/). Layout:")
w.table(["Path", "Contents", "Lines"], [
    [p, d, str(sum(len(f.read_text(errors='replace').splitlines())
                   for f in (ROOT / p).rglob("*") if f.is_file() and f.suffix in (".c", ".h", ".cpp", ".py", ".sh")
                   and "build" not in f.parts and ".mod." not in f.name))]
    for p, d in (("analyzer/src", "klg-analyze static analyser (C++)"),
                 ("runtime", "klg-agent fault-injection driver (C)"),
                 ("vm", "kernel/initramfs build, QEMU launcher, guest init"),
                 ("corpus", "benchmark modules and harness (C)"),
                 ("klg", "orchestrator, verifier, evaluation (Python)"),
                 ("dashboard", "Streamlit dashboard (Python)"))
], "Repository structure", widths=[3.5, 10, 2.5])
w.para("Key excerpt: the path search of the static analyser (analyzer/src/Analyzer.cpp).")
src = (ROOT / "analyzer" / "src" / "Analyzer.cpp").read_text().splitlines()
start = next(i for i, l in enumerate(src) if l.strip().startswith("void dfs(BasicBlock *BB"))
end = start + 1
depth = 0
for j in range(start, len(src)):
    depth += src[j].count("{") - src[j].count("}")
    if depth == 0 and j > start:
        end = j + 1
        break
w.code("\n".join(src[start:end]), size=8)

R.page_numbers(doc)
R.update_fields_on_open(doc)
out = DOCS / "KernelLeakGuard_Final_Report.docx"
doc.save(out)
print(f"wrote {out}")
