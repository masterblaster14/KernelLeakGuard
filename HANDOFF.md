# KernelLeakGuard — Project Handoff

Written 2026-10-15 for a new Claude Code session/account. Read this whole file
before changing anything. Everything listed as "done" was run and verified;
everything under "What is left" is NOT built yet.

---

## 1. Project in one paragraph

**KernelLeakGuard** is a BITE303P Operating Systems Lab project (VIT Vellore,
Fall 2026-27, 40 marks) that detects memory leaks on Linux kernel **early-exit
(error) paths** with an LLVM-based static analyser (C++, inspired by MLEE,
USENIX ATC 2021) and then **verifies every warning at runtime**: it boots a
custom Linux 6.18.55 kernel in QEMU/KVM, uses the kernel's per-task fault
injection (`/proc/thread-self/fail-nth`) to fail exactly the call that leads
onto the leaking path, and asks kmemleak whether an object allocated at the
reported site was left unreferenced. Each warning becomes **confirmed / not
reproduced / inconclusive** with evidence, and a **fix patch** is generated and
validated (compile + re-analysis + VM re-run).

- **Team:** Om Gunjan Gupta (24BIT0316) — static analyser; Abhishek Kumar Singh
  (24BIT0309) — kernel/VM/fault-injection agent; Aarav Jain (24BIT0023) — corpus,
  Python verifier, evaluation, dashboard.
- **Guide:** Dr. Arivuselvan K, Associate Professor, SCORE (on the cover the
  template prints it in capitals: "Dr. ARIVUSELVAN K").
- The user (Om Gunjan Gupta) wants it **fully working (not a demo)**, "no
  mistakes", and may later write a **research paper**.
- Course guidelines PDF and report template are in `docs/templates/`.

---

## 2. Where everything is

| What | Location |
|---|---|
| Project (code, results, doc generators) | WSL Ubuntu: `~/KernelLeakGuard` = `\\wsl.localhost\Ubuntu\home\gupta\KernelLeakGuard` |
| Kernel source / build tree | `~/klg-build/linux-6.18.55`, `~/klg-build/kbuild` (O= build dir), `~/klg-build/initramfs.cpio.gz` |
| cppcheck (local, no root) | `~/klg-build/tools/cppcheck` (installed by `scripts/install_cppcheck.sh`) |
| Final deliverables (Word + PDF) | `C:\Users\gupta\Downloads\KernelLeakGuard_Deliverables` and `~/KernelLeakGuard/docs/` |
| Original inputs from user | `docs/templates/` (VIT report template, guidelines PDF, initial project summary) |
| Claude memory note | `C:\Users\gupta\.claude\projects\C--Users-gupta\memory\kernelleakguard-project.md` |

**No git repository and no backup exist yet** (see "What is left", item B).

### Machine / environment
- Windows 11, AMD Ryzen 7 250 (16 threads), 15 GB RAM; WSL2 Ubuntu 26.04
  (WSL kernel 6.18), user `gupta`, member of `kvm` group, `/dev/kvm` works.
- Clang/LLVM 21.1.8, QEMU 10.2.1, Python 3.14; project venv at
  `~/KernelLeakGuard/.venv` (streamlit, pandas, matplotlib, python-docx,
  python-pptx, pymupdf). `sudo` asks for the user's password (Claude cannot
  type it — ask the user to run apt commands themselves).
- Microsoft Word + PowerPoint are installed on Windows (used for PDF export
  via COM in `scripts/export_pdf.ps1`).

### Tooling gotchas (important — these cost a lot of time)
1. **The Bash tool is Git Bash on Windows**: it mangles Linux paths and `$VARS`
   passed to `wsl`. Use the **PowerShell tool** with
   `wsl -d Ubuntu --cd /home/gupta/KernelLeakGuard -- <cmd>`.
2. **PowerShell breaks complex quoting** (`$`, nested quotes, `(`, `|` inside
   `bash -c "..."`). Reliable method: write a script file (e.g.
   `.scratch/s.sh` via the Write tool to
   `\\wsl.localhost\Ubuntu\home\gupta\KernelLeakGuard\.scratch\s.sh`) and run
   `wsl -d Ubuntu -- bash /home/gupta/KernelLeakGuard/.scratch/s.sh`.
3. **Editing files from Windows (Write/Edit tools) drops the Unix executable
   bit.** The Python code therefore always runs scripts as `bash script.sh`;
   keep it that way. `chmod +x vm/*.sh scripts/*.sh` if you run them directly.
4. **Never rebuild the kernel while a VM run is in progress** (the run uses
   `bzImage` and the module tree). After any kernel config change, re-run
   `python3 -m klg build` (rebuilds corpus modules against the new kernel).
5. Kernel rebuilds after a config change take 10–25 min; run in background.
6. Long tool outputs (big diffs) were twice cut off by a safety filter in the
   previous session; work in small steps and avoid dumping very large outputs.

---

## 3. How to run (all inside WSL, in `~/KernelLeakGuard`)

```bash
./vm/build_kernel.sh            # (only if kernel changes) builds Linux 6.18.55, LLVM=1
python3 -m klg all              # build → analyse (6 variants) → 3 VM runs → evaluate  (~5 min)
python3 -m klg fix              # generate + validate fix patches (1 VM run, ~2 min)
python3 -m klg show             # one line per finding with verdict
.venv/bin/streamlit run dashboard/app.py   # http://localhost:8501
bash scripts/repeat_runs.sh 3   # N independent full runs → results/runs/
bash scripts/build_docs.sh      # tests + figures + all Word/PPT documents
# then on Windows (PowerShell):
powershell -File \\wsl.localhost\Ubuntu\home\gupta\KernelLeakGuard\scripts\export_pdf.ps1 -Docs "\\wsl.localhost\Ubuntu\home\gupta\KernelLeakGuard\docs"
.venv/bin/python -m unittest discover -s tests -v   # 24 tests, all pass
```
Order that keeps documents consistent: `klg all` (or `repeat_runs.sh N`, the
last run's results are used) → `klg fix` → `build_docs.sh` → `export_pdf.ps1`
→ copy `docs/KernelLeakGuard_*` to the Downloads folder.

---

## 4. Architecture and every file

```
kernel module C ─► kbuild compile cmd + clang -emit-llvm -Xclang -disable-llvm-passes
               ─► klg-analyze (C++/LLVM) ─► candidates JSON (alloc, exit, errno, triggers, fix point)
QEMU/KVM guest (Linux 6.18.55 + kmemleak + fault injection), 3 runs:
   baseline run : unfiltered fail-nth sweep + kmemleak (exhaustive baseline) + random injection
   mapping run  : module-filtered fail-nth sweep (stack-trace filter) → fault N → source line
   confirm run  : inject the N that fails each candidate's trigger ×3, kmemleak → verdict
host: faddr2line / klg_modwatch symbol log → attribution → verdicts → evaluation, fixes, dashboard
```

### analyzer/ (C++17, LLVM 21) — `make -C analyzer` → `analyzer/build/klg-analyze`
- `src/Spec.{h,cpp}`: allocator / deallocator / non-escaping tables; name
  normalisation (strips `\01`, `.clone` suffixes, `_noprof`); `--spec extra.json`.
- `src/Analyzer.{h,cpp}`:
  - `prepare()`: folds calls to constant-returning stubs (e.g.
    `mem_alloc_profiling_enabled()` inside the kmalloc macro), mem2reg,
    LowerExpect, InstSimplify, ConstantFoldTerminator + removeUnreachableBlocks.
  - `FlowTracker`: alias closure (casts, GEPs, PHI, select, calls returning a
    param), field-sensitive stack "containers" (alloca + byte offset, -1 =
    unknown index), events Release / Escape / Return, `releaseLocs()`.
  - Summaries (monotone fixpoint): ReturnsAlloc, FreesParam, EscapesParam, ReturnsParam.
  - `SiteAnalysis`: DFS from allocation to returns; prunes the alloc-failed
    (NULL) edge; branch correlation with canonical `CondKey`; decisions seeded
    from dominating branches outside loops; loops visited ≤2× with stale
    decision ranges; re-execution of the allocation = "reallocated" instance;
    trigger detection (`controllingCall`, through IS_ERR and stack-slot reloads);
    exit description (errno names, propagated errors); confidence/category;
    `Fix` = first statement of the error branch + `FixExclusive`.
  - JSON: candidates with `alloc{file,line,col}`, `alloc_size`, `exit`,
    `exit_kind`, `return_value`, `confidence`, `category`, `triggers[]`,
    `path_lines`, `fix{file,line,col,exclusive}`, `release_sites[]`,
    `approximate`; plus `alloc_sites{function:[{file,line,allocator}]}` and `stats`.
  - Ablation flags: `--no-escape --no-interproc --no-corr --no-containers --naive`.
- `src/main.cpp`: CLI.

### runtime/
- `klg-agent.c` (static C, in guest): `sweep` (fail-nth 1,2,…, `--start N`,
  `--max`, `--filter MODULE`), `repeat` (`--nth N --count R`, `--expect FRAME`
  with ±window probing, `--random`, `--filter`). Writes `@@BEGIN n=` (flushed,
  for crash detection), `@@ATTEMPT n= ret= errno= injected=`, kernel log lines
  `K ...`, `@@END`, `@@MISS`. `--filter` sets require-start/require-end of
  failslab, fail_usercopy, fail_function to the module's code range (from
  `KLG-MOD` lines), with a dry-run load in init mode and re-sync if the module
  moves; restores the filter on exit.
- `modwatch/klg_modwatch.c`: module notifier; on MODULE_STATE_COMING logs
  `KLG-MOD <name> text=<b>+<s> init=<b>+<s>` and (once per layout) every
  function symbol `KLG-SYM <name> <addr> <sym>` from `mod->kallsyms`.

### vm/
- `kernel.config.fragment`: kmemleak (no auto-scan), FAULT_INJECTION + FAILSLAB
  + FAULT_INJECTION_USERCOPY + FAIL_FUNCTION + STACKTRACE_FILTER, ftrace-based
  kprobes (needed: int3 kprobes run in NMI-like context where fail-nth is
  ignored), ORC, DWARF5, no KASLR, `VMAP_STACK=n`, `KSTACK_ERASE=y`, virtio-9p.
- `real_modules.fragment`: **39 hardware-free real modules =m** (built, not yet evaluated).
- `build_kernel.sh` (defconfig + kvm_guest + both fragments, checks every option),
  `build_initramfs.sh` (busybox-static + init + klg-agent), `build_corpus.sh`,
  `env.sh` (paths), `init` (guest PID 1: mounts, configures fault injection
  verbose=2, ignore-gfp-wait=N, kmemleak scan=off and **stack=off**, runs
  `/mnt/host/job.sh`), `run_vm.sh` (QEMU/KVM 2 vCPU 2 GB, 9p share; cmdline
  includes `init_on_alloc=1 init_on_free=1` and `$KLG_EXTRA_CMDLINE`).

### corpus/ — benchmark (32 modules)
- `klg_l01..l17_*.c` leaky, `klg_s01..s15_*.c` safe; every allocation line has
  `/* GT:LEAK */` or `/* GT:SAFE */` (17 leak sites, 42 safe sites).
- `klg_harness.h`: `KLG_TRIGGER(fn)` / `KLG_TRIGGER_USER(fn)` → debugfs file
  `/sys/kernel/debug/klg_<module>`; modules without it are "init mode".
- `Kbuild` builds every `klg_*.c` (filters generated `*.mod.c`).

### klg/ (Python orchestrator; `python3 -m klg …`)
- `config.py` paths; `build.py` (modules, IR from `.cmd` files, `emit_ir(obj,
  out_dir, cwd=None)` — `cwd` param exists for in-tree objects, initramfs +
  modwatch build); `analyze.py` (variants); `ground_truth.py`.
- `evidence.py`: agent-log / kmemleak parsing, `faddr2line` (binutils mode,
  **no `/size`** — kallsyms sizes include padding), `(file,line)` locations,
  `KO_PATHS`, `SymbolMap` (resolves raw addresses of unloaded modules from
  KLG-MOD/KLG-SYM lines).
- `verify.py`: idempotent guest jobs (`next_n`, `done_*` markers), resilient
  `_run_vm` (watchdog `STALL_SECONDS=150`, `MAX_RESTARTS=25`, records
  `out/crashes.json` + crash consoles), sweeps, `fault_map`, `_match_points`
  (exact line → function fallback for merged debug info → silent faults),
  `plan_tests`, `schedule` (≤1 test per module per round, init tests alone),
  `confirm_job`, `judge` (exact loc / function fallback / size fallback /
  control leaks / crashed rounds), `dynamic_sites`, `run(...)` (parameters:
  `targets`, `gt`, `inject_fns`, `resilient`, `baselines`, `skip_sweep`).
- `evaluate.py`: metrics per allocation site; approaches `static/*`, `hybrid`,
  `klg/combined` (confirmed ∪ sweep leaks), `dynamic/exhaustive`,
  `dynamic/random`, `cppcheck` (maps "Memory leak: var" to the assigning line).
- `fix.py`: patch generation (reuse existing release statement / deallocator
  table / rollback loop for `x[i]`; brace insertion) + validation (compile,
  static re-analysis, VM module-filtered sweep with `slub_debug=FZPU`);
  statuses `validated`, `runtime-validated`, `failed`, `skipped`, `covered`.
- `figures.py` (matplotlib, validated palette, flowchart, architecture, terminal
  screenshots), `cli.py` (commands: build, analyze, verify, evaluate, fix,
  real, show, all), `__main__.py`.

### dashboard/app.py (Streamlit)
Sidebar pages: Overview, Findings (source view with alloc/fails/exit
highlighting, runtime evidence, patch), Fix patches, **Real kernel code**
(reads `results/real/...`, shows info message until it exists), Evaluation,
Run pipeline (background process via `start_new_session`, state in
`results/dashboard_run.json`, log `results/dashboard_run.log`, `@@EXIT n`
marker, live fragment refresh every 2 s, Stop button). Steps offered include
`fix` and `real` (`real` will fail until `klg/real.py` exists).

### tests/
- `test_klg.py` (21 tests: parsing, size matching, symbol map, crash site,
  planning, scheduling, ground truth, analyser regressions incl. ablations).
- `test_dashboard.py` (3 tests incl. clicking Run and waiting for exit 0).

### docs/
- `report_lib.py` (VIT formatting helpers, TOC field, page numbers, cover
  name/guide replacement `set_guide`, `tighten_cover`), `build_report.py`
  (final report from template; **all numbers read from results JSON**),
  `build_reviews.py` (Project Proposal + Review-I), `build_manual.py`,
  `build_ppt.py` (20 slides), `figures/`, `templates/`.
- Generated: `KernelLeakGuard_Final_Report` (33 pages), `_Project_Proposal`
  (4), `_Review1_Design_Progress` (8), `_User_Manual` (9), `_Presentation`
  (20 slides), each .docx/.pptx + .pdf.

### scripts/
`setup_venv.sh`, `install_cppcheck.sh`, `repeat_runs.sh`, `build_docs.sh`,
`export_pdf.ps1`, `render_pdf.py` (PDF → PNG sheets for visual review),
`try_static.py` (dev check of static results vs ground truth).

---

## 5. Current results (final run, 2026-10-13; stored in results/)

Benchmark: 32 modules, 17 leaking + 42 safe allocation sites.

| Approach | TP | FP | FN | Precision | Recall | Executions |
|---|---|---|---|---|---|---|
| Static, naive | 16 | 11 | 1 | 0.59 | 0.94 | – |
| Static, KernelLeakGuard | 16 | 1 | 1 | 0.94 | 0.94 | 27 ms analysis |
| Hybrid (confirmed warnings) | 14 | 0 | 3 | 1.00 | 0.82 | 425 (304 mapping + 121 confirm) |
| **KernelLeakGuard complete** | **16** | **0** | **1** | **1.00** | **0.94** | 425 |
| Dynamic, exhaustive FI | 15 | 0 | 2 | 1.00 | 0.88 | 1261 |
| Dynamic, random FI | 13 | 0 | 4 | 1.00 | 0.77 | 1600 |
| cppcheck 2.19 | 6 | 1 | 11 | 0.86 | 0.35 | – |

- 3 repeated runs: hybrid confirmed 15, 15, 14 (the variable one is the
  vmalloc leak L10 — kmemleak tracks vmalloc areas with min_count 2, so a stale
  copy hides it in a scan); complete tool 16/0/1 in all 3; no false positive ever.
- Static misses L16 (nested heap ownership) by design; S09 (correct rollback
  loop) is a static false positive refuted at runtime; L15 is inconclusive
  (ida_alloc never allocates for small IDs, failure cannot be injected).
- Ablation (F1): naive 0.73, no-escape 0.85, no-interproc 0.80,
  no-containers 0.90, no-corr 0.91, full 0.94.
- Fixes (final run): 13 fully validated + 1 runtime-validated (L04 rollback
  loop: leak gone in VM, analyser still flags it — loop-counter limitation) of
  14 confirmed leaks. Patches in `results/fixes/patches/`.
- System test cases: 29/32 pass (fails: L10 in the final run, L15, L16).
  Unit tests: 24/24 pass.

### Key engineering findings (already in the report)
- fail_function needs ftrace-based kprobes (int3 handler: `in_task()` false → fail-nth ignored).
- faddr2line must be called without `/size`; LLVM=1 mode of faddr2line breaks.
- Stale pointers hide leaks from kmemleak: fixed with VMAP_STACK=n,
  KSTACK_ERASE, kmemleak `stack=off`, `init_on_alloc=1 init_on_free=1`
  (`KSTACK_ERASE_TRACK_MIN_SIZE` < 100 breaks the build — early-boot PI code).
- Random baseline must set `task-filter` before `probability` (otherwise PID 1 gets faults → panic).
- Unrolled loops lose source lines → function-level fallback with single allocation site.
- Failed module init unloads the module before kmemleak prints → klg_modwatch.

---

## 5a. FINAL STATUS (2026-10-16) — read first

Done since the sections below were written:
- **Real-kernel evaluation done** (`python3 -m klg real`): static analysis of all
  39 modules (6376 functions, 590 allocation sites, 115 warnings); runtime run of
  15 representative modules under QEMU **software emulation (TCG)** because WSL
  lost hardware virtualization (Windows VBS still running even with Memory
  Integrity off; `.wslconfig` has `nestedVirtualization=true`). 6156 fault points
  exercised, 59 warnings: 58 inconclusive (mostly code not reachable from
  module init: mount/ioctl/netlink paths), 1 not reproduced, 0 confirmed.
- Manual review: `scripts/make_real_triage.py` → `results/real/triage.json`
  (13 reviewed in source = all high-confidence ones, all false positives;
  38 "likely false positive" by ERR_PTR pattern; 8 not reviewed).
- Findings to analyse further (paper material, NOT yet confirmed bugs):
  (1) reproducible kernel crash loading **null_blk** under allocation failure
  (page fault in bdev_release reading freed module memory; ~739th filtered fault
  point; sweep truncated after 10 crashes); (2) kmemleak report during **erofs**
  init: 21 kmem_cache name strings (kstrdup in __kmem_cache_create_args from
  z_erofs_create_pcluster_pool), likely a slab-core error path.
- Docs updated: report section 4.4 "Evaluation on Real Kernel Code" (Analysis is
  4.5), conclusion, future work, slide 15, README, manual. 27 tests pass.
- Git repo initialised, first commit by "Om Gupta <guptaom750@gmail.com>";
  the user does NOT want Claude listed as author/co-author. Not pushed
  (user's GitHub: github.com/masterblaster14 — push only if asked).
- Remaining optional work: run all 39 modules with KVM when available; model
  ERR_PTR/refcount to cut false positives; drive non-init entry points;
  root-cause the null_blk crash and erofs report and check upstream.

## 5b. PROGRESS UPDATE (2026-10-15)

- `klg/real.py` now EXISTS and works for the static part: `python3 -m klg real
  --skip-vm` analysed all 39 real modules → `results/real/static/full/*.json`,
  `results/real/summary.json` (6376 functions, 590 allocation sites, 115 static
  warnings). Options: `--skip-build`, `--skip-vm`, `--only a,b,c`.
- `verify.PRELOAD` (dependency preloading) is implemented and used by real.py
  (deps found: crc-itu-t, nls_ucs2_utils, zsmalloc, configfs, crc-t10dif,
  udp_tunnel, ip6_udp_tunnel).
- `build.emit_ir` now resolves out_dir to an absolute path (bug fix).
- `verify._run_vm` now stops immediately if the guest never booted (host/QEMU
  problem) instead of retrying it as a crash; `vm/run_vm.sh` falls back to TCG
  when KVM is not usable.
- **KVM stopped working** because Windows Memory Integrity (Core isolation)
  got enabled. The user switched it OFF; a **PC restart** is required. Also
  created `C:\Users\gupta\.wslconfig` with `nestedVirtualization=true`.
  After restart verify: `wsl -d Ubuntu -- bash /home/gupta/KernelLeakGuard/.scratch/kvm.sh`
  must print "svm flags: >0" and "KVM open OK".
- **Next steps after restart:**
  1. Pilot: `python3 -m klg real --skip-build --only dummy,minix,null_blk`
     (writes into results/real — fine, it will be overwritten by the full run).
  2. Full run: `python3 -m klg real --skip-build` (static reused, VM runs).
  3. Manual triage of the warnings, crashes and sweep leaks → `results/real/triage.json`.
  4. Docs (section 4.5 etc., see item A.10), README, manual, PPT; tests for real.py.
  5. Re-run `python3 -m klg all` + `klg fix` only if something in the corpus path changed.
  6. Git init + commit (user approved "build everything pending").

## 6. What is left — in detail

### A. Real Linux kernel module evaluation (`python3 -m klg real`) — NOT BUILT
**State:** the guest kernel already builds 39 hardware-free modules
(`vm/real_modules.fragment`: dummy, veth, netdevsim, bonding, macvlan, ipvlan,
nlmon, tun, vxlan, geneve, team, mac80211_hwsim, null_blk, brd, zram,
scsi_debug, dm-flakey, dm-dust, dm-delay, minix, romfs, cramfs, squashfs, udf,
nilfs2, jfs, f2fs, exfat, ntfs3, hfsplus, hfs, erofs, qnx4, ufs, omfs, affs,
snd-dummy, snd-aloop, uinput; IFB and VRF were dropped — their deps are not in
the config). `kbuild/modules.order` lists 55 modules. The CLI command `real`
is registered in `klg/cli.py` (`cmd_real` → `from . import real;
real.run(skip_build=..., skip_vm=...)`) but **`klg/real.py` does not exist**,
so `klg real` (and the dashboard step `real`) currently crash with ImportError.
The dashboard page "Real kernel code" is already written and expects the
files below.

**What to implement (`klg/real.py`):**
1. **Module discovery:** read `config.KBUILD / "modules.order"`; keep entries
   whose basename (without `.ko`/`.o`) is in the 39-module set; kernel module
   name = basename with `-` → `_`; `.ko` path = `KBUILD/<path>.ko`.
2. **Objects:** read `KBUILD/<path without .ko>.mod` (lists the module's
   object files, relative to KBUILD). Only C objects (check the `.cmd` source
   ends with `.c`).
3. **IR:** for each object `build.emit_ir(KBUILD/obj, outdir, cwd=config.KBUILD)`
   (in-tree compile commands are relative to the build dir; the `cwd` parameter
   already exists). Link with `llvm-link -o results/real/ir/<name>.bc *.bc`.
   Expect some objects to fail IR generation (flags) — log and skip, don't abort.
4. **Static:** `analyze.analyze_module(bc, name, out_dir=REAL/"static")` →
   `results/real/static/full/<name>.json`. Add `source_path` to each candidate
   (DILocation filename may be relative, e.g. `../linux-6.18.55/...`; resolve
   against KBUILD, then KSRC). Dashboard uses `c["source_path"]`.
   Watch analysis time / `approximate` flags on big modules (f2fs, ntfs3);
   `--max-steps` exists.
5. **Dependencies:** `modinfo -F depends <ko>` (comma list, recursive) →
   topological preload order. **Not implemented yet in verify.py:** add a
   module-level `PRELOAD: list[str]` (or a `preload` parameter) to
   `verify._job_setup` that emits `insmod /mnt/host/mods/<dep>.ko` right after
   klg_modwatch; make `_write_share` also copy the dependency `.ko`s; exclude
   from targets any module that is a dependency of another target (it stays
   loaded).
6. **Runtime:** targets = `verify.Target(name, "init", f"/mnt/host/mods/{name}.ko")`;
   `mods = {name: {"ko": ko, "src": first_source}}`;
   `verify.run(mods, reports, out_root=REAL/"runtime", baselines=False,
   targets=targets, gt=None, inject_fns=[], resilient=True)`.
   This runs the mapping sweep (module-filtered, kmemleak per module) and the
   confirmation run with crash/hang recovery (implemented but **never tested on
   real modules** — test on 2–3 small modules first, e.g. dummy, minix, null_blk).
   Check: `SWEEP_MAX_INIT=1500` may be too small for big init paths;
   `STALL_SECONDS=150`; guest RAM 2 GB (scsi_debug/brd/zram may need params or
   more RAM); crash entries land in `verification.json["crashes"]`.
7. **Outputs expected by the dashboard:**
   - `results/real/static/full/*.json`, `results/real/runtime/verification.json`
   - `results/real/summary.json` with keys: `modules`, `functions`,
     `fault_points` (sum of mapping executions), `crashes` (count), `headline`
     (markdown sentence), `dynamic_leaks` (list of dicts from
     `verification["sweep_leaks"]`: module, file, line, objects, size, backtrace).
   - `results/real/triage.json`: list of `{"id", "label", "note"}` written by
     a human/Claude after **manually reviewing each warning** in the kernel
     source (label: true leak / false positive / unclear) and each crash.
8. **Manual triage:** read every static warning and every sweep leak / crash
   in the actual source (`~/klg-build/linux-6.18.55/...`). If a genuine leak or
   crash is found: confirm on the latest upstream kernel before claiming
   anything; this would be the strongest result for the paper.
9. **Tests:** unit tests for discovery, `.mod` parsing, dependency ordering.
10. **Documents after it works:** add report section "4.5 Evaluation on real
    kernel code" (modules, functions, warnings, verdicts, triage, crashes,
    time), update abstract, conclusion, limitations, remove it from future
    work (report `build_report.py` future-work list, PPT slide 19), add a PPT
    slide, README + user manual (`klg real`). Keep every number generated
    from JSON like the rest of `build_report.py`. Regenerate with
    `build_docs.sh`, export PDFs, visually check with `scripts/render_pdf.py`,
    copy to Downloads.

### B. Version history and backup — NOT DONE (guidelines require version history)
- `git init` in `~/KernelLeakGuard`; `.gitignore` already exists (ignores
  build outputs, `.venv`, `.scratch`, `results/ir`, runtime shares). Commit
  only when the user approves; ask before pushing to GitHub. Commit
  attribution lines per the session's instructions.
- Suggest a backup copy of `~/KernelLeakGuard` to Windows/USB.

### C. Smaller open items
- **Review-I document** is written as a progress snapshot (some items "In
  progress"); the user should adjust wording to the actual submission date.
- **Dashboard screenshot** is not in the report (no headless browser
  available); the user can take one (Win+Shift+S) and it can be inserted.
- The user should open the final report .docx in Word once (TOC refresh) and
  check the cover.
- `README.md` does not yet mention `klg fix` and `klg real`; the user manual
  covers `klg fix`.

### D. Known limitations / possible research improvements
- Field-sensitive heap ownership (L16 nested buffer missed statically).
- Loop-counter / value-range reasoning (S09 false positive; L04 patch still flagged).
- vmalloc leaks are flaky under kmemleak (min_count 2) — e.g. repeat scans or
  multiple rounds before declaring "not reproduced".
- Fix patches for shared error labels (non-exclusive branches) are skipped.
- Reproduce historical MLEE-reported leaks on older kernels (would need older
  kernel builds).
- Benchmark is self-written; for a paper, real-code results (item A) are essential.

---

## 7. Rules the user gave
- Everything must genuinely work; no fake/demo results; no mistakes.
- Use names exactly: **Om Gunjan Gupta**, **Dr. Arivuselvan K** (Associate
  Professor, SCORE).
- User has limited credits: prefer efficient, verified steps; report honestly
  (including failures and run-to-run variation).
- Commit/push only when the user asks.
