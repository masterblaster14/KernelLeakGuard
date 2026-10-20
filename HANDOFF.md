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

---

## 4. KVM status (important for runtime speed)

Hardware virtualization stopped working inside WSL because Windows
virtualization-based security (VBS) is running. The user turned **Memory
Integrity off** and restarted, and `nestedVirtualization=true` is set, but
`Win32_DeviceGuard VirtualizationBasedSecurityStatus` was still 2 (running).

`vm/run_vm.sh` therefore falls back to **TCG software emulation**
(`-accel tcg,thread=multi -cpu max`). Results are correct but 10–20× slower.
`verify.py` raises `STALL_SECONDS` to 900 under TCG.

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
.venv/bin/python -m unittest tests.test_klg tests.test_dashboard   # 27 tests
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
4. `make_real_triage.py`
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
- **`seed.py`** (NEW): seeded-bug evaluation, driven by `seeds/*.json`.
  - Comments out one release statement **inside the named function** (`_func_range` skips forward declarations).
  - Builds the module out-of-tree with `-I$(srctree)/<module dir>` for private headers.
  - Diffs the warnings against the **unmodified baseline** build, so pre-existing warnings don't count.
  - Optionally confirms in the VM. The fix is the re-inserted statement, which equals the baseline, validated statically (and in the VM unless `--skip-vm`).
- **`figures.py`, `cli.py`** (commands: build, analyze, verify, evaluate, fix, real, seed, show, all).

### Dashboard, tests, scripts, docs

- **`dashboard/app.py`** (Streamlit). Pages: Overview, Findings, Fix patches, Real kernel code, Evaluation, Run pipeline. The Run button works: it runs a background process with live log and a Stop button.
- **`tests/`**: `test_klg.py` (24, including real-module discovery and ordering) and `test_dashboard.py` (3). **27 in total, all pass.**
- **`scripts/`**: `setup_venv.sh`, `install_cppcheck.sh`, `repeat_runs.sh`, `build_docs.sh`, `export_pdf.ps1`, `render_pdf.py`, `try_static.py` (corpus static check, expected `TP=16 FN=1 FP=1`), `make_real_triage.py` (hand-review labels in its `REVIEWED` dict).
- **`docs/`**: `report_lib.py`, `build_report.py`, `build_reviews.py` (proposal and Review-I), `build_manual.py`, `build_ppt.py`, `figures/`, `templates/`.

**`.scratch/`** (git-ignored) contains helper scripts:
- `reanalyze.py`
- `check_all.py` (name check)
- `kvm.sh`
- `finalize.sh` (seed, triage, docs, name check)
- `ship.sh` (copy to Downloads, commit)

---

## 7. Results (all reproducible from results/)

### 7.1 Benchmark corpus (final run 2026-10-13, unchanged by later work)

32 modules: 17 leaking allocation sites and 42 safe ones.

| Approach | TP | FP | FN | Precision | Recall | Executions |
|---|---|---|---|---|---|---|
| Static, naive | 16 | 11 | 1 | 0.59 | 0.94 | – |
| Static, KernelLeakGuard | 16 | 1 | 1 | 0.94 | 0.94 | ~27 ms |
| Hybrid (confirmed warnings) | 14 | 0 | 3 | 1.00 | 0.82 | 425 |
| **KernelLeakGuard complete** | **16** | **0** | **1** | **1.00** | **0.94** | 425 |
| Dynamic, exhaustive fault injection | 15 | 0 | 2 | 1.00 | 0.88 | 1261 |
| Dynamic, random fault injection | 13 | 0 | 4 | 1.00 | 0.77 | 1600 |
| cppcheck 2.19 | 6 | 1 | 11 | 0.86 | 0.35 | – |

- **Three repeated runs:**
  - The hybrid approach confirmed 15, 15 and 14 leaks. The variation comes from the vmalloc leak L10: kmemleak tracks vmalloc with min_count 2.
  - The complete tool scored 16/0/1 every time, with **never a false positive**.
- **Known misses and false positives:**
  - L16 (nested heap ownership) is missed statically, by design.
  - S09 (a correct rollback loop) is a static false positive that the runtime check refutes.
  - L15 is inconclusive: ida_alloc doesn't allocate for small IDs.
- **Ablation F1:** naive 0.73, no-escape 0.85, no-interproc 0.80, no-containers 0.90, no-corr 0.91, full 0.94.
- **Fixes:** 13 validated and 1 runtime-validated (L04) of 14 confirmed leaks.
- **System test cases:** 29 of 32 pass.

### 7.2 Real Linux 6.18.55 modules (final re-run 2026-10-16, TCG)

**Static analysis:** 39 modules, 6376 functions, 590 allocation sites, **64 warnings**.
- Before ERR_PTR modelling there were 115 warnings.
- The change did not alter any corpus result.

**Runtime:** 15 representative modules:
- null_blk, minix, bonding, vxlan, tun, mac80211_hwsim, brd, zram
- scsi_debug, dm_dust, squashfs, hfs, erofs, snd_aloop, uinput

Runtime results:
- 6166 fault points of module init were exercised.
- **30 warnings, all inconclusive; 0 confirmed.** Most warnings sit in mount, ioctl or netlink code that init-time testing never reaches.

**Manual triage** (`results/real/triage.json`):
- 12 false positives, reviewed in source.
- 10 likely false positives (by pattern).
- 8 not reviewed.
- Remaining false-positive causes: reference-counted lookups (`hfs_bnode_find` + put), error codes held in a variable (snd_aloop `err < 0` at a shared label), struct field plus escape (mac80211_hwsim), release through list iteration (scsi_debug).

**Found by the tool on real code. These are observations, NOT confirmed bugs:**
1. **null_blk:** a reproducible kernel crash under allocation failure during init. It is a page fault in `bdev_release` reading freed module memory (deferred `__fput`). The sweep was truncated after 10 crashes.
2. **erofs init:** a kmemleak report of 21 kstrdup'd kmem_cache name strings (32 B each), allocated in `__kmem_cache_create_args` from `z_erofs_create_pcluster_pool` (zdata.c:466). erofs's own cleanup looks correct, so the cause is likely a slab-core error path.

Neither has been root-caused or checked upstream.

**Seeded bug** (`klg seed`, `seeds/brd_blk_alloc_disk.json`):
- `brd_free_device(brd);` was removed in `brd_alloc()`, brd.c:350.
- **Detected:** a new warning appeared — allocation at line 317 (`brd_find_or_alloc_device`), exit at line 351.
- **Fix validated statically.**
- **Not confirmed in the VM:** brd's init crashes the kernel under fault injection, and each reboot clears kmemleak.
- A scsi_debug seed was tried and dropped: `sdbg_host` is passed to `sdebug_device_create`, so the analyser treats it as escaped and doesn't flag the leak.

### 7.3 Key engineering findings (all in the report)

- fail_function needs **ftrace-based kprobes**. In int3 kprobes, `in_task()` is false, so fail-nth is ignored.
- faddr2line must be called **without `/size`**; its LLVM=1 mode breaks.
- **Stale pointers hide leaks from kmemleak.** Fixed with VMAP_STACK=n, KSTACK_ERASE, kmemleak `stack=off`, and `init_on_alloc=1 init_on_free=1`.
- The random baseline must set `task-filter` **before** `probability`. Otherwise PID 1 gets faults and the kernel panics.
- When a module's init fails, the module is unloaded before kmemleak reports. `klg_modwatch` solves this.
- Kernel lookup helpers return ERR_PTR, not NULL. Modelling `IS_ERR` removed 44% of the real-code false positives.

---

## 8. Documents (all DONE, in the Downloads folder as .docx/.pptx + .pdf)

| Document | Pages | Notes |
|---|---|---|
| Final Report | 37 | Chapter 4: 4.1–4.3 benchmark, **4.4 Real kernel code** (with the ERR_PTR paragraph, runtime table, triage, erofs, null_blk crash trace), **4.5 Seeded leaks** (brd table + honest note that VM confirmation wasn't possible), **4.6 Analysis**; conclusion; future work |
| Project Proposal | 4 | |
| Review-I Design/Progress | 8 | A progress snapshot: the user may adjust wording to the submission date |
| User Manual | 9 | Includes `klg fix`, `klg real`, `klg seed` |
| Presentation | 20 slides | Slide 14 = verdicts + ablation; slide 15 = real kernel code (precision fix, seeded leak, crash, erofs) |

Names were verified in every file by `.scratch/check_all.py`. The user should
open the report in Word once so the table of contents refreshes, and check the
cover. No dashboard screenshot is in the report: the user can take one with
Win+Shift+S and it can be inserted.

---

## 9. Git

- Repository: `~/KernelLeakGuard`, branch `master`.
- Commits:
  - `41ec0ce` (initial)
  - `82a182f` "Model ERR_PTR returns; add seeded-bug evaluation on real kernel modules"
- Both authored by Om Gupta <guptaom750@gmail.com>, with no Claude attribution.
- Two more commits follow: "Consolidate project handoff document" and "Ignore seed harness build products". Run `git log --oneline` for the current list.
- `.gitignore` excludes:
  - build outputs, `.venv`, `.scratch`, `results/ir`
  - VM shares and mappings, `results/real/ir`, `results/fixes/build|runtime`
  - modwatch build outputs
  - seed-harness build products and VM runs. The seed sources, reports and `result.json` stay tracked.
- **Not pushed.** To push, once the user approves:
  1. Create the repository on GitHub, e.g. `masterblaster14/KernelLeakGuard`.
  2. `git remote add origin https://github.com/masterblaster14/KernelLeakGuard.git && git push -u origin master`
  3. The user must authenticate, using `gh auth login` or a token.

Check `du -sh .git` before pushing; it was about 13 MB at the first commit.

---

## 10. What is left (priority order)

The course deliverables are complete. These items would strengthen the demo
and a future paper.

1. **One seeded leak CONFIRMED in the VM, on real code.** This is the
   strongest demo item still missing.
   - Needs KVM (see section 4), or a crash-robust module whose init-time
     allocation is not handed to a helper.
   - The brd seed's leak fault points were mapped (n=11, 13, 15 at brd_alloc),
     but crashes at other fault points wiped kmemleak.
   - Ideas:
     - Raise `MAX_CRASHES_PER_LOG` for seeds.
     - Load brd with `rd_nr=1`; the agent passes "" to finit_module, so the agent needs to accept module parameters.
     - Add a targeted confirm that injects only the mapped N without a full sweep.
     - Loosen `_match_points` so a trigger call line matches the frame line of the fault inside that call.
2. **Root-cause the null_blk crash and the erofs kmemleak report.** Read
   `drivers/block/null_blk/main.c` init error paths, `block/bdev.c`
   `bdev_release`, `mm/slab_common.c` `__kmem_cache_create_args`, and erofs
   `z_erofs_create_pcluster_pool`/`z_erofs_destroy_pcluster_pool`. If either
   turns out to be genuine, check it on the latest upstream kernel. It would be
   the headline result for a paper (and possibly an upstream patch).
3. **Further cut real-code false positives:** model reference-counted lookups
   (functions returning an object released by `*_put`), error-code-in-variable
   correlation (`if (err < 0)` at a shared label), and release via list
   iteration (`list_for_each_entry_safe` + kfree).
4. **Drive non-init entry points** (mount images, ioctl/netlink programs, or
   syzkaller-style programs) so the 30 inconclusive warnings become testable.
5. **Run all 39 modules in the VM** once KVM works: `python3 -m klg real --skip-build`.
6. Small items:
   - a dashboard screenshot for the report;
   - Review-I wording;
   - a backup copy of the project to Windows/USB, or a GitHub push when the user asks.

After any change, use the order in section 5. Re-check the corpus with
`python3 scripts/try_static.py full` (must stay `TP=16 FN=1 FP=1`) and run
the 27 tests, then regenerate the documents and copy them to Downloads.

---

## 11. History of the work (short)

1. Built the analyser, VM, agent, corpus, verifier, evaluation, dashboard,
   fixes and documents.
2. Fixed the dashboard Run button and the names everywhere.
3. Real-kernel evaluation (2026-10-15/16): KVM was lost because of VBS, so
   the user chose a representative subset under TCG.
4. Git initialised.
5. The user asked "isn't MLEE already working on real kernel code, the
   professor needs to see it working". Response: ERR_PTR modelling (115 → 64
   warnings), the `klg seed` harness, a real re-run, and docs updated with an
   honest account (detected and fixed on real code; VM confirmation obstructed
   by brd crashes).
