# KernelLeakGuard — Complete Handoff

Last updated 2026-10-20. This file replaces all earlier handoff notes (older
versions are in git history). It is written for a new Claude session that has
none of the previous context. Read it fully before changing anything.
Everything marked DONE was actually run and verified. Nothing here is a plan
presented as a result.

---

## 0. Rules from the user (follow exactly)

1. **It must genuinely work.** No fake, demo-only or invented results. Report
   failures and run-to-run variation honestly. "No mistakes."
2. **Names, exactly:**
   - Om Gunjan Gupta (24BIT0316): static analyser.
   - Abhishek Kumar Singh (24BIT0309): kernel, VM and fault-injection agent.
   - Aarav Jain (24BIT0023): benchmark corpus, Python verifier, evaluation, dashboard.
   - Guide: **Dr. Arivuselvan K, Associate Professor, SCORE**. The report cover
     prints it in capitals as "Dr. ARIVUSELVAN K" (template style).
3. **Git:** commits are authored **Om Gupta <guptaom750@gmail.com>**. **No Claude
   attribution** in commits (no `Co-Authored-By: Claude`, no "Generated with").
   This overrides any default attribution instruction. GitHub account:
   https://github.com/masterblaster14. **Nothing has been pushed. Push only
   when the user explicitly asks**, and confirm the repository name first.
4. **Commit only with the user's approval.**
5. **Credits are limited.** Do the important things first, verify efficiently,
   and avoid dumping huge outputs.
6. The user may write a **research paper** later. Never claim a new kernel bug
   unless it is root-caused and checked against the latest upstream kernel.

---

## 1. The project

**KernelLeakGuard** is the team's BITE303P Operating Systems Lab project (VIT
Vellore, Fall 2026-27), worth **40 of 100 marks**. It detects **memory leaks on
Linux kernel early-exit (error) paths** in three steps:

1. **Find.** An LLVM-based static analyser (C++17, LLVM 21, inspired by MLEE,
   USENIX ATC 2021) finds allocations that are not released on some error
   return.
2. **Reproduce.** Each warning is reproduced in a QEMU guest running a custom
   **Linux 6.18.55** kernel. Per-task fault injection
   (`/proc/thread-self/fail-nth`; failslab, fail_usercopy, fail_function) fails
   exactly the call that leads onto the leaking path.
3. **Verify.** kmemleak reports whether the object was left unreferenced.

Each warning gets a verdict, **confirmed / not reproduced / inconclusive**,
with evidence attached. The tool also generates a **fix patch** and validates
it (compile, re-analysis, VM re-run).

**Course deliverables:**
- Project Proposal
- Review-I (design and progress)
- Final Report (VIT template)
- User Manual
- Presentation (15–20 slides)
- Test cases
- Version history (git)

All of these are **done**. The course guidelines PDF and the report template
are in `docs/templates/`.

---

## 2. Where everything is

| What | Location |
|---|---|
| Project code, results, doc generators | WSL Ubuntu `~/KernelLeakGuard`. From Windows: `\\wsl.localhost\Ubuntu\home\gupta\KernelLeakGuard` |
| Kernel source and build tree | `~/klg-build/linux-6.18.55` (KSRC), `~/klg-build/kbuild` (KBUILD, the O= dir) |
| Guest initramfs | `~/klg-build/initramfs.cpio.gz` |
| cppcheck (local install) | `~/klg-build/tools/cppcheck` |
| Final deliverables (Word, PDF, PPT, this file) | `C:\Users\gupta\Downloads\KernelLeakGuard_Deliverables` (11 files) and `~/KernelLeakGuard/docs/` |
| Old Claude Code memory note | `C:\Users\gupta\.claude\projects\C--Users-gupta\memory\kernelleakguard-project.md` |
| WSL config created for KVM | `C:\Users\gupta\.wslconfig` (`[wsl2] nestedVirtualization=true`) |
| Kernel patches for the bugs found | `~/KernelLeakGuard/patches/0001..0004-*.patch` (with commit messages; NOT sent upstream) |
| Guest kernel with the SLUB fix | `~/klg-build/kbuild-slubfix` (bzImage only; built by `scripts/build_patched_kernel.sh`) |

**Machine:**
- Windows 11, AMD Ryzen 7 250 (16 threads), 15 GB RAM.
- WSL2 Ubuntu 26.04, user `gupta`.
- Clang/LLVM 21.1.8, QEMU 10.2.1, Python 3.14.
- Project venv: `~/KernelLeakGuard/.venv` (streamlit, pandas, matplotlib, python-docx, python-pptx, pymupdf).
- `sudo` needs the user's password. Claude cannot type it, so ask the user to run any `apt` commands.
- Microsoft Word and PowerPoint are installed. PDF export uses COM in `scripts/export_pdf.ps1`.

**If you are the Claude desktop/web app:** you need filesystem and terminal
access to the WSL folder above, for example through Claude Code. A chat-only
session cannot run anything; it can only advise.

---

## 3. Tooling gotchas (each of these cost hours)

1. **The Bash tool in Claude Code on Windows is Git Bash.** It mangles Linux
   paths and `$VARS` passed to `wsl`. Use PowerShell:
   `wsl -d Ubuntu --cd /home/gupta/KernelLeakGuard -- <cmd>`
2. **PowerShell breaks inline quoting.** `$`, nested quotes and `[ ]` inside
   `bash -c "python3 -c ..."` fail every time. Always write a script file to
   `\\wsl.localhost\Ubuntu\home\gupta\KernelLeakGuard\.scratch\x.sh`, then run
   `wsl -d Ubuntu -- bash /home/gupta/KernelLeakGuard/.scratch/x.sh`
3. **Editing from Windows drops the executable bit.** Always run scripts as
   `bash script.sh`.
4. **`make` may not notice edits made from Windows** (timestamps). After editing
   `analyzer/src/*.cpp`, run `touch analyzer/src/Analyzer.cpp && make -C analyzer`
   and confirm that a compile line is printed.
5. **`pkill -f 'klg real'` kills its own shell** because the pattern matches
   its own command line. Use `pgrep -f "^python3 -m klg real"` or kill by PID.
6. **Run long VM jobs detached inside WSL:**
   `setsid nohup bash -c "python3 -m klg real ... > results/x.log 2>&1" &`
   A tool timeout would otherwise kill them.
7. **Never rebuild the kernel or initramfs while a VM run is in progress.**
   `klg seed` and `klg build` rebuild the initramfs, so run them only when no
   VM job is active.
8. **`klg real --skip-build` reuses the cached static JSON files** in
   `results/real/static/full/`. After changing the analyser, refresh them
   first: `python3 .scratch/reanalyze.py` re-runs klg-analyze on the existing
   bitcode in `results/real/ir/`. You can also drop `--skip-build`, which is
   slower.
9. **Long outputs were cut off by a safety filter** several times. Work in
   small steps.
10. **Claude Code may also run directly inside WSL** (session of 2026-10-20). Then the
    Bash tool is real Linux bash and items 1-3 do not apply. PowerShell is reachable from
    WSL as `powershell.exe` (used for the PDF export).
11. **Stall detector:** `verify._run_vm` reboots the guest when nothing in `out/` changes
    for 900 s (TCG). Touching a file in `out/` resets that clock.
12. **Skipping a module that keeps hanging:** write `10` into
    `results/real/runtime/mapping/out/crashes_sweep_<module>`; the job's own truncation
    rule then skips it after the next reboot (done for snd_dummy on 2026-10-20, after 4 hangs).
13. **git.kernel.org rate-limits** after a few dozen requests (connection refused for a
    while). `raw.githubusercontent.com/torvalds/linux/master/...` and
    `github.com/torvalds/linux/commit/<id>.patch` work as fallbacks.
14. **`reanalyze.py` takes ~3-5 min**; do not wrap it in a short `timeout`, or the static
    files end up half old, half new. It prints `TOTAL n` when complete.
15. **Analyser changes invalidate the corpus runtime results:** `klg evaluate` then fails with
    a KeyError for a vanished warning id. Re-run `klg analyze --all-variants`,
    `klg verify --skip-sweep`, `klg evaluate`, `klg fix` (the baselines are reused).
16. **`klg real` without `--only` runs all 39 modules in the VM** (about 3 h under TCG).
    After a static-only analyser change with an unchanged warning set,
    `python3 scripts/rejudge_real.py` + `python3 -m klg real --skip-build --skip-vm`
    refresh verdict reasons and the summary without the VM.

---

## 4. KVM status (important for runtime speed)

Hardware virtualization stopped working inside WSL because Windows
virtualization-based security (VBS) is running. The user turned **Memory
Integrity off** and restarted, and `nestedVirtualization=true` is set, but
`Win32_DeviceGuard VirtualizationBasedSecurityStatus` was still 2 (running).

`vm/run_vm.sh` therefore falls back to **TCG software emulation**
(`-accel tcg,thread=multi -cpu max`). Results are correct but 10–20× slower.
`verify.py` raises `STALL_SECONDS` to 900 under TCG.

**Diagnosed 2026-10-20:** `Win32_DeviceGuard` shows VBS running (status 2) with **no**
security services running (Memory Integrity and Credential Guard off). Setting
`HKLM\SYSTEM\CurrentControlSet\Control\DeviceGuard\EnableVirtualizationBasedSecurity = 0`
and restarting did NOT stop VBS: **Windows Hello Enhanced Sign-in Security**
(`...\DeviceGuard\Scenarios\WindowsHello\Enabled = 1`) keeps it on. Turning that off
(Settings → Accounts → Sign-in options → "Sign in with an external camera or fingerprint
reader" ON, re-enrol face/fingerprint, restart) should free KVM, at the cost of the VBS
isolation of the biometric sign-in. **The user decided to skip KVM**: all results are complete
under TCG. The user restored the registry value to 1 afterwards, so Windows is back to its
original configuration.

**Check KVM:** `wsl -d Ubuntu -- bash /home/gupta/KernelLeakGuard/.scratch/kvm.sh`.
It must print "svm flags: >0" and "KVM open OK".

**To get KVM back:** the user must fully disable VBS. Options are Windows
Security → Core isolation, and possibly turning off "Virtual Machine
Platform"/Hyper-V-dependent features or Credential Guard (Windows Defender
Credential Guard / System Guard), then reboot. With KVM, all 39 real modules
can run in the VM: `python3 -m klg real --skip-build`.

---

## 5. How to run (inside WSL, in `~/KernelLeakGuard`)

```bash
./vm/build_kernel.sh            # only after kernel config changes (10–25 min)
python3 -m klg all              # corpus: build → analyse (6 variants) → VM runs → evaluate
python3 -m klg fix              # generate + validate fix patches
python3 -m klg show             # one line per finding with verdict
python3 -m klg real [--only a,b] [--skip-build] [--skip-vm]   # real kernel modules
python3 -m klg seed [--only name] [--skip-vm]                 # seeded-bug evaluation
python3 scripts/make_real_triage.py      # manual-review labels → results/real/triage.json
.venv/bin/streamlit run dashboard/app.py # dashboard, http://localhost:8501
bash scripts/repeat_runs.sh 3            # N independent full corpus runs
bash scripts/build_docs.sh               # unit tests + figures + all Word/PPT docs
.venv/bin/python -m unittest tests.test_klg tests.test_dashboard   # 32 tests
python3 scripts/make_root_causes.py      # real-kernel findings → results/real/root_causes.json
python3 scripts/fault_probe.py MOD LO HI BATCH OUT    # probe init fault points (kmemleak+dmesg)
bash scripts/build_patched_kernel.sh PATCH OUT_KBUILD # guest kernel with one patch, own O= dir
python3 scripts/validate_patch.py MOD DIR FILE PATCHED_FILE OUT   # static patch validation
bash scripts/regress.sh SCRATCH_DIR     # analyser regression: 6 corpus variants + real diff
```

**PDF export, from Windows PowerShell:**

```powershell
& "\\wsl.localhost\Ubuntu\home\gupta\KernelLeakGuard\scripts\export_pdf.ps1" -Docs "\\wsl.localhost\Ubuntu\home\gupta\KernelLeakGuard\docs"
```

**Visual check:** `.venv/bin/python scripts/render_pdf.py docs/KernelLeakGuard_Final_Report.pdf .scratch/p/r 1 6 --grid 6`

**Name check:** `.venv/bin/python .scratch/check_all.py`

**Order that keeps the documents consistent:**
1. `klg all`
2. `klg fix`
3. `klg real` / `klg seed`
4. `make_real_triage.py`, `make_root_causes.py`
5. `build_docs.sh`
6. `export_pdf.ps1`
7. Copy `docs/KernelLeakGuard_*` and `HANDOFF.md` to the Downloads folder.

`build_report.py` and `build_ppt.py` read every number from the results JSON.
**Never hard-code numbers**, except the single "115 before ERR_PTR modelling"
figure, which was measured once.

---

## 6. Architecture and files

```
module C ─► kbuild compile cmd + clang -emit-llvm -Xclang -disable-llvm-passes ─► llvm-link
        ─► klg-analyze (C++/LLVM) ─► candidates JSON (alloc, exit, errno, triggers, fix point)
QEMU guest (Linux 6.18.55 + kmemleak + fault injection):
  mapping run  : module-filtered fail-nth sweep (stack-trace filter) → fault N → source line
  confirm run  : inject the N that fails each candidate's trigger ×3, kmemleak → verdict
  (corpus also) baseline run: unfiltered exhaustive sweep + random injection
host: faddr2line / klg_modwatch symbol log → attribution → verdicts → evaluation, fixes, dashboard
```

### analyzer/

C++17, LLVM 21. Build with `make -C analyzer`, which produces `analyzer/build/klg-analyze`.

- **`src/Spec.{h,cpp}`**
  - Tables of allocators, deallocators and non-escaping functions.
  - Name normalisation: `.clone`/`.NN` suffixes, `_noprof`.
  - `--spec extra.json` adds custom allocators and deallocators.
- **`src/Analyzer.{h,cpp}`**
  - `prepare()`: folds constant stubs, then runs mem2reg, LowerExpect, InstSimplify and unreachable-block removal.
  - `FlowTracker`: alias closure, field-sensitive stack containers, and events (Release / Escape / Return).
  - Interprocedural summaries: ReturnsAlloc, FreesParam, EscapesParam, ReturnsParam.
  - `SiteAnalysis`: depth-first search from the allocation to each return.
    - Prunes the NULL edge (allocation failed).
    - **NEW, 2026-10-16:** `errPtrTest()` also prunes the `IS_ERR(tracked)`-true edge, where the pointer is an ERR_PTR error code.
    - Branch correlation (`CondKey`), dominating-decision seeding, loops visited at most twice.
    - Trigger detection (`controllingCall`), errno description, confidence and category, fix point.
  - **NEW, 2026-10-20 (all general rules; benchmark unchanged in all 6 variants):**
    - `returnsOtherOnPath()`: a return of `phi(obj, NULL)` hands obj over only on paths that
      bring obj into the phi (fixed a false negative; found via the null_blk seed). `undef`
      incoming = infeasible edge.
    - `PublishesParam` summary + `FlowTracker::publishes()`: a helper that stores the new
      object outside the function (list_add_tail, hash insert, global) before returning it is
      a lookup, not an allocator (`ReturnsAlloc` is a second fixpoint after the param facts).
      Stores into a scratch object allocated in the same function do not count.
    - `constantOnPath()` + switch handling: a branch/switch whose condition is constant along
      the path (clang cleanup-destination switch; `ConstantFoldTerminator` turns one-case
      switches into `br icmp eq`) has one feasible successor; condition keys are compared on
      path-resolved values (`err` phi vs the call result).
    - `Spec::transfersOnSuccess()` (register_netdevice, register_netdev): ownership passes only
      on the success edge of the branch on the call's result (`Pending` in `SiteAnalysis`).
    - Spec additions: `badblocks_init/exit` non-escaping; `alloc_netdev_mqs`,
      `alloc_etherdev_mqs` allocators; `free_netdev` deallocator.
    - Real-code warnings: 115 → 64 (ERR_PTR) → 42 (publish rule) → 11 (constant conditions);
      see `results/real/precision_history.json`.
  - Ablation flags: `--naive --no-escape --no-interproc --no-corr --no-containers`.
- **`src/main.cpp`**: command-line interface.

### runtime/

- **`klg-agent.c`** (static binary, runs in the guest)
  - `sweep`: fail-nth 1, 2, …; `--filter MODULE` sets the stack-trace filter to the module's code range.
  - `repeat`: `--nth N --count R --expect FRAME`, plus `--random`.
  - Log markers: `@@BEGIN`, `@@ATTEMPT`, `@@END`.
- **`modwatch/klg_modwatch.c`**: module notifier that logs `KLG-MOD` load addresses and `KLG-SYM` symbols, so leaks from modules that were already unloaded can still be symbolised.

### vm/

- **`kernel.config.fragment`**
  - kmemleak, FAULT_INJECTION, FAILSLAB, USERCOPY, FAIL_FUNCTION, STACKTRACE_FILTER.
  - **ftrace-based kprobes** (required).
  - ORC, DWARF5, no KASLR, VMAP_STACK=n, KSTACK_ERASE=y, virtio-9p.
- **`real_modules.fragment`**: 39 hardware-free real modules built as `=m`. IFB and VRF were dropped because their dependencies are missing.
- **Build scripts:** `build_kernel.sh`, `build_initramfs.sh`, `build_corpus.sh`, `env.sh`.
- **`init`** (guest PID 1): kmemleak with scan=off and **stack=off**; fault-injection verbose=2.
- **`run_vm.sh`**
  - QEMU with 2 vCPU and 2 GB RAM, 9p host share.
  - Kernel cmdline adds `init_on_alloc=1 init_on_free=1 $KLG_EXTRA_CMDLINE`.
  - Falls back to TCG when KVM is unusable.

### corpus/

32 benchmark modules: `klg_l01..l17` leak, `klg_s01..s15` are safe.

- Every allocation line is annotated `/* GT:LEAK */` or `/* GT:SAFE */`: 17 leak sites and 42 safe sites.
- `klg_harness.h` provides `KLG_TRIGGER(fn)`, which exposes a routine as a debugfs trigger. Modules without it run in "init mode".

### klg/

Python orchestrator, run as `python3 -m klg …`.

- **`config.py`**: paths.
- **`build.py`**: `emit_ir(obj, out_dir, cwd=None)`; resolves out_dir to an absolute path.
- **`analyze.py`, `ground_truth.py`**.
- **`evidence.py`**
  - Parses agent logs and kmemleak reports.
  - `faddr2line` is called **without `/size`**.
  - `SymbolMap` (from KLG-MOD/KLG-SYM lines), `KO_PATHS`.
- **`verify.py`**
  - Idempotent guest jobs.
  - Resilient `_run_vm`: crash/hang recovery, `MAX_RESTARTS=200`, `MAX_CRASHES_PER_LOG=10` (after that the sweep is truncated), `STALL_SECONDS` 150 (900 under TCG). A host QEMU failure aborts immediately.
  - `PRELOAD` dict for dependency modules.
  - Then fault_map, matching, plan, schedule, confirm, judge, and `run(...)`.
- **`evaluate.py`**: approaches static/*, hybrid, klg/combined, dynamic exhaustive/random, cppcheck.
- **`fix.py`**: patch generation and validation. Statuses: validated, runtime-validated, failed, skipped, covered.
- **`real.py`**: real-module evaluation.
  - Module discovery from `modules.order`, objects from `.mod` files.
  - IR via `emit_ir(cwd=KBUILD)` plus llvm-link; dependencies via `modinfo` and topological order.
  - Writes `results/real/summary.json`. Static statistics always cover all 39 modules, even with `--only`.
- **`seed.py`**: seeded-bug evaluation, driven by `seeds/*.json`. Spec fields added
  2026-10-20: `module` (multi-file modules: whole source dir is copied and built with its own
  Makefile; IR of all objects is llvm-linked), `sweep_max`, `vm: false` + `vm_note`,
  `history` (upstream commit of a real historical bug). `summary.json` always covers every
  seed; `--skip-vm` keeps earlier VM results (fixed-module runtime is in `runtime_fixed/`).
  - Comments out one release statement **inside the named function** (`_func_range` skips forward declarations).
  - Builds the module out-of-tree with `-I$(srctree)/<module dir>` for private headers.
  - Diffs the warnings against the **unmodified baseline** build, so pre-existing warnings don't count.
  - Optionally confirms in the VM. The fix is the re-inserted statement, which equals the baseline, validated statically (and in the VM unless `--skip-vm`).
- **`figures.py`, `cli.py`** (commands: build, analyze, verify, evaluate, fix, real, seed, show, all).

### Dashboard, tests, scripts, docs

- **`dashboard/app.py`** (Streamlit). Pages: Overview, Findings, Fix patches, Real kernel code, Evaluation, Run pipeline. The Run button works: it runs a background process with live log and a Stop button.
- **`tests/`**: `test_klg.py` (24, including real-module discovery and ordering) and `test_dashboard.py` (3). **27 in total, all pass.**
- **`scripts/`**: `setup_venv.sh`, `install_cppcheck.sh`, `repeat_runs.sh`, `build_docs.sh`, `export_pdf.ps1`, `render_pdf.py`, `try_static.py` (corpus static check, expected `TP=16 FN=1 FP=1`), `make_real_triage.py` (hand-review labels in its `REVIEWED` dict, keyed by (module, function, alloc line[, exit line])), `make_root_causes.py`, `fault_probe.py` (`PROBE_KBUILD`, `PROBE_KO`, `PROBE_CMDLINE` env overrides), `build_patched_kernel.sh`, `validate_patch.py`, `rejudge_real.py`.
- **`tests/analyzer_cases/klg_cases.c`**: user-space C cases for the real-code patterns, compiled like kbuild IR by `TestRealCodePatterns` (needs clang).
- **`patches/`**: 0001 SLUB, 0002 ntfs3, 0003 f2fs, 0004 ufs (see 7.2).
- **`docs/`**: `report_lib.py`, `build_report.py`, `build_reviews.py` (proposal and Review-I), `build_manual.py`, `build_ppt.py`, `figures/`, `templates/`.

**`.scratch/`** (git-ignored) contains helper scripts:
- `reanalyze.py`
- `check_all.py` (name check)
- `kvm.sh`
- `finalize.sh` (seed, triage, docs, name check)
- `ship.sh` (copy to Downloads, commit)

---

## 7. Results (all reproducible from results/)

### 7.1 Benchmark corpus (re-run 2026-10-20 with the final analyser: analyze, verify --skip-sweep, evaluate, fix; baselines from 2026-10-13 reused)

32 modules: 17 leaking allocation sites and 42 safe ones.

| Approach | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| Static, naive | 16 | 11 | 1 | 0.59 | 0.94 | 0.73 |
| Static, KernelLeakGuard | 16 | 1 | 1 | 0.94 | 0.94 | 0.94 |
| Hybrid (confirmed warnings) | 15 | 0 | 2 | 1.00 | 0.88 | 0.94 |
| **KernelLeakGuard complete** | **16** | **0** | **1** | **1.00** | **0.94** | **0.97** |
| Dynamic, exhaustive fault injection | 15 | 0 | 2 | 1.00 | 0.88 | 0.94 |
| Dynamic, random fault injection | 13 | 0 | 4 | 1.00 | 0.77 | 0.87 |
| cppcheck 2.19 | 6 | 1 | 11 | 0.86 | 0.35 | 0.50 |

- Ablation F1 unchanged: naive 0.73, no-escape 0.85, no-interproc 0.80, no-containers 0.90, no-corr 0.91, full 0.94.
- Fixes: **14 validated + 1 runtime-validated (l04) of 15 confirmed leaks**.
- The final analyser drops two low-confidence corpus warnings on impossible paths
  (`klg_l04:19:28`, `klg_s09:20:29`); site-level results are identical.
- Known misses: L16 (nested heap ownership), S09 static FP refuted at runtime, L15 inconclusive.
- Earlier repeated runs (old analyser): hybrid 15/15/14 confirmed, complete tool always 16/0/1.

### 7.2 Real Linux 6.18.55 modules (2026-10-20, TCG, ALL 39 modules in the VM)

`results/real/summary.json`: 39 modules, 6376 functions, 518 allocation sites, **11 static
warnings** (115 → 64 → 42 → 11, `precision_history.json`); 9779 init fault points
exercised; 11 inconclusive / 0 confirmed; **10 leak sites found by the sweep**; 15 guest
crashes/hangs (null_blk 10 crashes, snd_dummy 5 hangs; snd_dummy sweep stopped early by
hand, gotcha 12). Triage (`triage.json`): all 11 read in source: **2 real bugs**, 9 false
positives (value-in-memory, pointer identity, loop counters, async ownership).

**Kernel defects found (all root-caused and checked against mainline 7.3 on 2026-10-20;
evidence in `results/real/root_causes.json`; NOTHING sent upstream yet):**

| # | Defect | Found by | Status / fix |
|---|---|---|---|
| 1 | **SLUB slab-cache leak**: `sysfs_slab_add()` returns before `kobject_init_and_add()` when `create_unique_id()` fails; `kmem_cache_destroy()` then `kobject_put()`s an uninitialised kobject → cache + nodes + name leak | runtime sweep (erofs, f2fs, hfsplus, nilfs2 init) | in mainline + linux-next; `patches/0001` validated in VM: 20 → 0 leaked objects (`erofs_bisect` vs `erofs_slubfix`) |
| 2 | **f2fs `f2fs_init_sysfs()`** skips `kobject_put()` for the kobject whose `kobject_init_and_add()` failed → "features"/"tuning" names leak. Introduced by b635f2ecdb (2026-04-10, backported to stable) | runtime sweep | in mainline; `patches/0003` validated in VM: 29 → 0 (`f2fs_stock` vs `f2fs_patched`) |
| 3 | **ntfs3 `do_action()`** leaks the kzalloc'd `mft_inode` when `mi_format_new()` fails (log replay) | static (high confidence) | in mainline + next, no report found; `patches/0002` statically validated; not runtime-confirmed (needs crafted NTFS image) |
| 4 | **ufs `ubh_bforget()`** never frees the `ufs_buffer_head` (only caller `free_full_branch()`) | static | in mainline; same fix proposed 2018 (Luis Henriques, "ufs: Fix memory leak in the unlink path"), never merged; `patches/0004` statically validated |
| 5 | **null_blk / block-layer use-after-free**: `disk_scan_partitions()` defers the final `__fput()` to task_work; when init then fails (fault 739: `configfs_register_subsystem()`), the module is freed and `bdev_release()` reads freed `disk->fops` | runtime sweep (crash) | in mainline; reproduced at 739/741/743/745 on a fresh guest; NO fix validated (`__fput_sync()` is for kthreads only) |

Rule 6 caveat: before any paper/upstream claim, search lore.kernel.org for pending patches.

**Leaks re-introduced into real modules (`results/seeded/summary.json`): 2/2 detected,
confirmed by kmemleak in the VM, fixed (VM re-run clean), 0 crashes:**
- `bonding_bond_create_8d6184e4881b`: **real historical bug** (shipped until 2010, fixed by
  8d6184e4881b): `free_netdev()` removed from `bond_create()`'s `register_netdevice()`
  failure path; kmemleak reports the 4096-byte net_device from `alloc_netdev_mqs()`.
- `null_blk_alloc_dev`: seeded by us (`kfree(dev)` removed in `null_alloc_dev()`).
- Rejected seeds (in the report): brd (object stays on a global list → not a leak), zram and
  scsi_debug (escape via IDR / registering helper), scsi_debug e6d773f93a49 (leaked name is
  allocated in the driver core; also its sweep reached only 4 fault points — unexplained).

### 7.3 Key engineering findings (all in the report)

- fail_function needs **ftrace-based kprobes**. In int3 kprobes, `in_task()` is false, so fail-nth is ignored.
- faddr2line must be called **without `/size`**; its LLVM=1 mode breaks.
- **Stale pointers hide leaks from kmemleak.** Fixed with VMAP_STACK=n, KSTACK_ERASE, kmemleak `stack=off`, and `init_on_alloc=1 init_on_free=1`.
- The random baseline must set `task-filter` **before** `probability`. Otherwise PID 1 gets faults and the kernel panics.
- When a module's init fails, the module is unloaded before kmemleak reports. `klg_modwatch` solves this.
- Kernel lookup helpers return ERR_PTR, not NULL. Modelling `IS_ERR` removed 44% of the real-code false positives.
- kbuild IR keeps `static inline` helpers as calls (`list_add_tail`), and `ConstantFoldTerminator` turns one-case cleanup switches into `br icmp eq`; both matter for path feasibility.
- The guest console runs at `loglevel=4`: WARNs and fault-injection stacks are only visible with `PROBE_CMDLINE=loglevel=8` or in `dmesg`.

---

## 8. Documents (all DONE 2026-10-20, in the Downloads folder as .docx/.pptx + .pdf)

| Document | Pages | Notes |
|---|---|---|
| Final Report | 41 | Abstract includes the real-code results. 3.2.1 describes the new analyser rules. **4.4 Real kernel code**: precision table (115→11), all-39-module runtime table, manual review, sweep leaks, root causes of SLUB / f2fs / ntfs3 / ufs / null_blk. **4.5 Re-introduced leaks**: bonding (historical, 8d6184e4881b) + null_blk, rejected seeds. Conclusion + future work updated |
| Project Proposal | 4 | |
| Review-I Design/Progress | 8 | A progress snapshot: the user may adjust wording to the submission date |
| User Manual | 10 | Includes `klg seed` fields, triage/root-cause scripts, fault-probe helpers |
| Presentation | 20 slides | Slide 14 = verdicts + ablation; slide 15 = real kernel code (refinements, re-introduced leaks, SLUB, f2fs, ntfs3/ufs, null_blk) |

Every number is read from `results/` by the generators. Names verified by
`.scratch/check_all.py`. Open the report in Word once so the table of contents refreshes.
The dashboard's **Real kernel code** page shows the root causes, patches and seeded leaks;
its Run page has a `seed` step.

---

## 9. Git

- Repository: `~/KernelLeakGuard`, branch `master`, authored Om Gupta <guptaom750@gmail.com>,
  no Claude attribution. Last commit before this session: `2a65037`.
- The 2026-10-20 work is committed (one commit, user-approved): run `git log --oneline`.
- `.gitignore` now also excludes `results/real/*/mods/` (module copies in probe shares).
- **Not pushed.** To push, once the user approves: create `masterblaster14/KernelLeakGuard`,
  `git remote add origin https://github.com/masterblaster14/KernelLeakGuard.git && git push -u origin master`;
  the user must authenticate (`gh auth login` or a token). Check `du -sh .git` first.

---

## 10. What is left (priority order)

1. ~~Commit the 2026-10-20 work~~ DONE (user approved).
2. **Runtime-confirm a real, still-present bug through the whole loop.** Candidates: ntfs3
   `do_action` (needs an NTFS image whose $LogFile replays InitializeFileRecordSegment for an
   unreadable record) or ufs (mounted UFS image + truncate). Needs a mount mode in the agent
   (handoff item "drive non-init entry points").
3. **Drive non-init entry points** (mount images, ioctl/netlink programs): makes most
   remaining warnings and historical fill_super leak fixes (udf, romfs, squashfs, exfat,
   nilfs2, jfs …) testable.
4. **More historical bugs**: the git.kernel.org log search (`log/<path>?qt=grep&q=leak`)
   listed many; only init-path ones are usable today. Use `seeds/*.json` with `history`.
5. **Upstream (user's decision):** patches 0001/0003/0004/0002 are ready with commit messages;
   search lore for pending fixes first; null_blk UAF needs a maintainer discussion.
6. snd_dummy hangs under fault injection (5 hangs, not analysed); scsi_debug sweep reaches
   only 4 fault points (unexplained).
7. KVM (section 4; skipped by the user) would make all VM work 10-20x faster.
8. Small: dashboard screenshot for the report; Review-I wording.

After any analyser change: `bash scripts/regress.sh DIR` (6 corpus variants must stay as in
7.1; the real-code diff must be explained), the 32 tests, then gotcha 15/16, then section 5's
order, `make_real_triage.py`, `make_root_causes.py`, `build_docs.sh`, PDF export, copy.

---

## 11. History of the work (short)

1. Built the analyser, VM, agent, corpus, verifier, evaluation, dashboard,
   fixes and documents.
2. Fixed the dashboard Run button and the names everywhere.
3. Real-kernel evaluation (2026-10-15/16): KVM was lost because of VBS, so
   the user chose a representative subset under TCG.
4. Git initialised.
5. ERR_PTR modelling (115 → 64 warnings), the `klg seed` harness, a real re-run.
6. 2026-10-20 (Claude Code inside WSL): brd seed shown unconfirmable; null_blk seed
   confirmed in the VM; analyser: phi-return false negative, ownership of published objects,
   constant-condition path resolution, conditional ownership transfer, netdev alloc/free
   (64 → 11 real warnings, benchmark unchanged); all 39 modules run in the VM; root-caused
   SLUB, f2fs (regression from b635f2ecdb), null_blk UAF; static finds ntfs3 + ufs; patches
   0001-0004 with VM/static validation; bonding historical bug through the full loop;
   corpus verify/fix re-run; all docs regenerated.
