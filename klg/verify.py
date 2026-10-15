"""Runtime verification of static leak candidates inside the QEMU guest.

VM runs (each a fresh boot of the guest kernel):

1. Baseline run (dynamic-only approaches, optional). Every routine is run
   once per fault point (fail-nth = 1, 2, ...) with no filter, then kmemleak
   is scanned: exhaustive single-fault injection. Then random fault injection
   with a fixed budget.

2. Mapping run (hybrid). The same sweep, but fail-nth counts only fault points
   with the target module on the call stack (stack-trace filter), so only the
   module's own fault points are visited. The stack trace of each injected
   fault gives a map  N -> source location of the failing call. Leaks the
   sweep leaves behind are reported too.

3. Confirmation run. For each static candidate the fault number that fails
   one of its trigger calls is injected REPEAT times and kmemleak decides:
   CONFIRMED (an object allocated at the candidate's allocation site leaked),
   NOT REPRODUCED (the predicted failure was injected, nothing leaked) or
   INCONCLUSIVE (the failure could not be injected).

Guest jobs are idempotent: if the guest kernel crashes or hangs (possible
when failing allocations in real kernel code), the host records the crash,
reboots the VM and the job resumes after the fault point that caused it.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import config, evidence, ground_truth

REPEAT = 3                # executions per confirmation test
RANDOM_BUDGET = 50        # executions per module for the random baseline
RANDOM_PROBABILITY = 10   # percent
SWEEP_MAX_TRIGGER = 200
SWEEP_MAX_INIT = 1500
KMEMLEAK_SETTLE = 6       # seconds; kmemleak ignores objects younger than 5 s
STALL_SECONDS = 150       # no progress in the guest for this long = hang
if not Path("/dev/kvm").exists() or "svm" not in Path("/proc/cpuinfo").read_text() \
        and "vmx" not in Path("/proc/cpuinfo").read_text():
    STALL_SECONDS = 900   # software emulation (TCG) is ~10-20x slower
MAX_RESTARTS = 200        # per VM run (resumable jobs; real modules may crash often)
MAX_CRASHES_PER_LOG = 10  # then the rest of that module's sweep is skipped

Loc = evidence.Loc


# ---------------------------------------------------------------------------
# Guest job generation
# ---------------------------------------------------------------------------

@dataclass
class Target:
    module: str
    mode: str          # "trigger" | "init"
    path: str          # path inside the guest

    @staticmethod
    def of(module: str, src: Path) -> "Target":
        if ground_truth.init_mode(src):
            return Target(module, "init", f"/mnt/host/mods/{module}.ko")
        return Target(module, "trigger", f"/sys/kernel/debug/klg_{module}")


JOB_PROLOGUE = r"""
D=/sys/kernel/debug
OUT=/mnt/host/out
export D OUT
log() { echo "[job $(cut -d' ' -f1 /proc/uptime)] $*"; }
kml_scan() { sleep {settle}; echo scan > $D/kmemleak; echo scan > $D/kmemleak; }
# next_n LOG: fault number to resume a sweep at (after a crash: skip the
# attempt that was running when the guest died).
next_n() { [ -f "$1" ] || { echo 1; return; }
  n=$(grep -o '^@@BEGIN n=[0-9]*' "$1" | tail -1 | cut -d= -f2); echo $(( ${n:-0} + 1 )); }
"""


def error_injectable(src_dir: Path) -> list[str]:
    names = []
    for src in sorted(src_dir.glob("klg_*.c")):
        names += re.findall(r"ALLOW_ERROR_INJECTION\((\w+)", src.read_text())
    return names


MODWATCH = config.ROOT / "runtime" / "modwatch" / "klg_modwatch.ko"

# Modules the targets depend on, in load order: {name: .ko path}. They are
# copied to the share and loaded once at the start of every guest job.
PRELOAD: dict[str, Path] = {}


def _job_setup(targets: list[Target], inject_fns: list[str]) -> list[str]:
    lines = [JOB_PROLOGUE.replace("{settle}", str(KMEMLEAK_SETTLE))]
    # Logs module load addresses/symbols so leaks in unloaded modules resolve.
    lines.append("insmod /mnt/host/mods/klg_modwatch.ko || log 'insmod klg_modwatch failed'")
    for dep in PRELOAD:
        lines.append(f"insmod /mnt/host/mods/{dep}.ko || log 'insmod {dep} failed'")
    for t in targets:
        if t.mode == "trigger":
            lines.append(f"insmod /mnt/host/mods/{t.module}.ko || log 'insmod {t.module} failed'")
    for fn in inject_fns:
        lines.append(f"echo {fn} >> $D/fail_function/inject 2>/dev/null || log 'fei {fn} failed'")
    # Start from a clean slate: report (and then forget) pre-existing objects.
    lines += ["kml_scan", "cat $D/kmemleak >> $OUT/kmemleak_boot.txt", "echo clear > $D/kmemleak"]
    return lines


def _write_share(share: Path, mods: dict[str, dict], job: list[str]):
    if share.exists():
        shutil.rmtree(share)
    (share / "out").mkdir(parents=True)
    (share / "mods").mkdir()
    for name, m in mods.items():
        shutil.copy(m["ko"], share / "mods" / f"{name}.ko")
    for name, ko in PRELOAD.items():
        shutil.copy(ko, share / "mods" / f"{name}.ko")
    shutil.copy(MODWATCH, share / "mods" / "klg_modwatch.ko")
    (share / "job.sh").write_text("\n".join(job) + "\nlog done\n")


def _latest_mtime(d: Path) -> float:
    return max((p.stat().st_mtime for p in d.rglob("*") if p.is_file()), default=0.0)


def _run_vm(share: Path, timeout: int = 3600, resilient: bool = False,
            extra_cmdline: str = "") -> float:
    """Boot the guest on `share`. With resilient=True, a crash or hang is
    recorded in out/crashes.json and the (idempotent) job is restarted."""
    t0 = start = time.time()
    crashes = []
    env = dict(os.environ, KLG_EXTRA_CMDLINE=extra_cmdline)
    for attempt in range(MAX_RESTARTS + 1):
        proc = subprocess.Popen(["bash", str(config.ROOT / "vm" / "run_vm.sh"), str(share),
                                 str(timeout)], stdout=subprocess.DEVNULL, env=env,
                                stderr=subprocess.DEVNULL, start_new_session=True)
        stalled = False
        while proc.poll() is None:
            time.sleep(2)
            if time.time() - max(_latest_mtime(share / "out"), start) > STALL_SECONDS:
                stalled = True
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
        console = (share / "console.log").read_text(errors="replace") \
            if (share / "console.log").exists() else ""
        if "KLG-JOB-EXIT" in console:
            break
        if "KLG-GUEST-READY" not in console and not stalled:
            # The guest never booted: a host problem (e.g. KVM unavailable),
            # not a kernel crash. Retrying would not help.
            raise RuntimeError("QEMU could not start the guest: "
                               + " | ".join(console.strip().splitlines()[-3:]))
        if not resilient:
            raise RuntimeError(f"VM run failed; see {share / 'console.log'}")
        crash = {"restart": attempt + 1, "kind": "hang" if stalled else "crash",
                 "where": _crash_site(share / "out"),
                 "console": _panic_excerpt(console)}
        crashes.append(crash)
        if crash["where"].get("log"):
            # Count crashes per agent log; the job skips a module after too many.
            cnt = share / "out" / f"crashes_{crash['where']['log']}"
            cnt.write_text(str(int(cnt.read_text()) + 1 if cnt.exists() else 1))
        (share / f"console_crash{attempt + 1}.log").write_text(console)
        (share / "out" / "crashes.json").write_text(json.dumps(crashes, indent=2))
        start = time.time()
    else:
        raise RuntimeError(f"guest kept crashing; see {share}")
    return time.time() - t0


def _crash_site(out: Path) -> dict:
    """The agent log whose last line is a @@BEGIN marker = the running attempt."""
    newest = None
    for log in out.glob("*.log"):
        lines = log.read_text(errors="replace").rstrip().splitlines()
        if lines and lines[-1].startswith("@@BEGIN"):
            if newest is None or log.stat().st_mtime > newest[0]:
                newest = (log.stat().st_mtime, log.stem, lines[-1].split("=")[1])
    return {"log": newest[1], "fail_nth": int(newest[2])} if newest else {}


def _panic_excerpt(console: str) -> list[str]:
    lines = console.splitlines()
    for i, l in enumerate(lines):
        if re.search(r"(BUG:|Oops|general protection|Kernel panic|WARNING:|watchdog)", l):
            return [re.sub(r"^\[\s*\d+\.\d+\]\s*", "", x) for x in lines[i:i + 40]]
    return [re.sub(r"^\[\s*\d+\.\d+\]\s*", "", x) for x in lines[-25:]]


# ---------------------------------------------------------------------------
# Sweeps: fault point maps and dynamic baselines
# ---------------------------------------------------------------------------

def sweep_lines(targets: list[Target], filtered: bool) -> list[str]:
    """Visit every fault point of every target once (resumable).

    filtered=False: all fault points (exhaustive dynamic baseline).
    filtered=True : only fault points with the target module on the call
                    stack (the hybrid's fault-point map; far fewer runs).
    """
    job = []
    for t in targets:
        mx = SWEEP_MAX_INIT if t.mode == "init" else SWEEP_MAX_TRIGGER
        flt = f" --filter {t.module}" if filtered else ""
        log = f"$OUT/sweep_{t.module}.log"
        body = [f"log sweep {t.module}",
                f"klg-agent sweep --mode {t.mode} --target {t.path} --max {mx}{flt} "
                f"--start $(next_n {log}) --out {log}"]
        if t.mode == "init":
            # The module is unloaded after each failed init and the next module
            # may reuse its addresses: scan now so leaks map to this module.
            body += ["kml_scan", f"cat $D/kmemleak >> $OUT/kmemleak_sweep_{t.module}.txt",
                     "echo clear > $D/kmemleak"]
        body.append(f"touch $OUT/done_sweep_{t.module}")
        cnt = f"$OUT/crashes_sweep_{t.module}"
        job.append(f"if [ -f {cnt} ] && [ $(cat {cnt}) -ge {MAX_CRASHES_PER_LOG} ]; then "
                   f"log 'sweep {t.module} stopped after repeated guest crashes'; "
                   f"touch $OUT/done_sweep_{t.module} $OUT/truncated_sweep_{t.module}; fi")
        job.append(f"if [ ! -f $OUT/done_sweep_{t.module} ]; then\n  " + "\n  ".join(body) + "\nfi")
    job += ["if [ ! -f $OUT/done_scan ]; then log scan-exhaustive; kml_scan; "
            "cat $D/kmemleak > $OUT/kmemleak_exhaustive.txt; echo clear > $D/kmemleak; "
            "touch $OUT/done_scan; fi"]
    return job


def mapping_job(targets: list[Target], inject_fns: list[str]) -> list[str]:
    return _job_setup(targets, inject_fns) + sweep_lines(targets, filtered=True)


def sweep_job(targets: list[Target], inject_fns: list[str]) -> list[str]:
    """Dynamic-only baselines: exhaustive and random fault injection."""
    job = _job_setup(targets, inject_fns) + sweep_lines(targets, filtered=False)
    # Random fault injection baseline (no static guidance). Order matters:
    # restrict injection to opted-in tasks (task-filter) BEFORE raising the
    # probability, otherwise PID 1 and this shell get faults too.
    job.append("for f in failslab fail_usercopy fail_function; do "
               "echo Y > $D/$f/task-filter; echo 0 > $D/$f/verbose; done")
    job.append("for f in failslab fail_usercopy fail_function; do "
               f"echo {RANDOM_PROBABILITY} > $D/$f/probability; done")
    for t in targets:
        job.append(f"log random {t.module}")
        job.append(f"klg-agent repeat --random --mode {t.mode} --target {t.path} --nth 0 "
                   f"--count {RANDOM_BUDGET} --out $OUT/random_{t.module}.log")
    job.append("for f in failslab fail_usercopy fail_function; do "
               "echo 0 > $D/$f/probability; echo 2 > $D/$f/verbose; done")
    job += ["log scan-random", "kml_scan",
            "cat $D/kmemleak > $OUT/kmemleak_random.txt", "echo clear > $D/kmemleak"]
    return job


# ---------------------------------------------------------------------------
# Fault point maps and test planning
# ---------------------------------------------------------------------------

@dataclass
class FaultPoint:
    n: int
    locs: list[Loc]           # module source locations on the fault's stack
    frames: list[str]         # matching module frames ("func+0x1a/0xe0")
    ret: int
    errno: int
    traced: bool = True       # False: injected silently (__GFP_NOWARN)
    # Module functions on the stack whose address has no source location
    # (merged debug locations, e.g. after loop unrolling): name -> frame
    unresolved: dict[str, str] = field(default_factory=dict)


def fault_map(module: str, sweep_log: Path) -> list[FaultPoint]:
    points = []
    for a in evidence.parse_agent_log(sweep_log):
        if not a.injected:
            continue
        locs, frames, unresolved = [], [], {}
        for fr in a.fault_frames():
            if fr.module != module:
                continue
            ls = evidence.frame_locs(fr)
            locs += ls
            frames += [fr.text] * len(ls)
            if not ls:
                unresolved.setdefault(fr.func, fr.text)
        points.append(FaultPoint(a.n, locs, frames, a.ret, a.errno, a.traced(), unresolved))
    return points


def _match_points(c: dict, points: list[FaultPoint], alloc_sites: dict
                  ) -> tuple[list[tuple[FaultPoint, str | None]], str]:
    """Fault points that make one of the candidate's trigger calls fail.

    Returns [(point, expected frame)] and how they were matched.
    """
    trig = c["triggers"]
    # 1. Exact: a frame of the fault's stack is the trigger call's location.
    for t in reversed(trig):                      # primary trigger first
        want = evidence.loc_of(t)
        hits = [(fp, fp.frames[fp.locs.index(want)]) for fp in points if want in fp.locs]
        if hits:
            return hits, "line"
    # 2. Function: the frame resolves only to the candidate's function, and
    #    that function has exactly one allocation site, the trigger.
    only = evidence.single_site(alloc_sites, c["function"])
    for t in reversed(trig):
        if t["kind"] == "alloc" and only == evidence.loc_of(t):
            hits = [(fp, fp.unresolved[c["function"]]) for fp in points
                    if c["function"] in fp.unresolved]
            if hits:
                return hits, "function"
    # 3. Silent: faults injected without a stack trace that made the routine
    #    fail. The site is not observable; kmemleak decides.
    hits = [(fp, None) for fp in points if not fp.traced and fp.ret < 0]
    if trig and hits:
        return hits, "silent"
    return [], ""


@dataclass
class Test:
    tid: str
    module: str
    mode: str
    target: str
    n: int
    expect: str | None
    candidates: list[str] = field(default_factory=list)


def plan_tests(candidates: list[dict], fmaps: dict[str, list[FaultPoint]],
               targets: dict[str, Target],
               reports: dict[str, dict]) -> tuple[list[Test], dict[str, dict]]:
    """Choose fault points that steer execution onto each candidate's path."""
    tests: dict[tuple[str, int], Test] = {}
    plan: dict[str, dict] = {}
    for c in candidates:
        mod = c["module"]
        trig = [f"{Path(t.get('file', '')).name}:{t['line']}" for t in c["triggers"]]
        if mod not in targets:
            plan[c["id"]] = {"status": "inconclusive", "reason": "module has no runtime target"}
            continue
        if not trig:
            plan[c["id"]] = {"status": "inconclusive",
                             "reason": "no failing call controls the leaking path"}
            continue
        alloc_sites = reports.get(mod, {}).get("alloc_sites", {})
        chosen, how = _match_points(c, fmaps.get(mod, []), alloc_sites)
        if not chosen:
            plan[c["id"]] = {"status": "inconclusive",
                             "reason": f"no fault point reaches the failing call ({', '.join(trig)})"}
            continue
        chosen = chosen[:3]
        plan[c["id"]] = {"status": "planned", "match": how,
                         "fault_points": [fp.n for fp, _ in chosen]}
        for fp, frame in chosen:
            key = (mod, fp.n)
            if key not in tests:
                t = targets[mod]
                tests[key] = Test(f"{mod}__n{fp.n}", mod, t.mode, t.path, fp.n, frame)
            tests[key].candidates.append(c["id"])
    # One control run (no fault) per module with candidates.
    for mod in sorted({c["module"] for c in candidates if c["module"] in targets}):
        t = targets[mod]
        tests[(mod, 0)] = Test(f"{mod}__control", mod, t.mode, t.path, 0, None)
    return list(tests.values()), plan


def schedule(tests: list[Test]) -> list[list[Test]]:
    """Rounds in which leaks can be attributed unambiguously: at most one
    test per module, and init-mode tests alone (their module is unloaded
    before the scan and the next module may reuse its addresses)."""
    rounds: list[list[Test]] = []
    for t in sorted(tests, key=lambda x: (x.mode != "init", x.module, x.n)):
        if t.mode == "init":
            rounds.append([t])
            continue
        for r in rounds:
            if r[0].mode != "init" and all(o.module != t.module for o in r):
                r.append(t)
                break
        else:
            rounds.append([t])
    return rounds


def confirm_job(rounds: list[list[Test]], targets: list[Target], inject_fns: list[str]) -> list[str]:
    job = _job_setup(targets, inject_fns)
    for i, rnd in enumerate(rounds):
        body = [f"log round {i}", f"touch $OUT/start_round_{i}"]
        for t in rnd:
            exp = f" --expect '{t.expect}'" if t.expect else ""
            flt = f" --filter {t.module}" if t.n else ""      # same numbering as the map
            body.append(f"klg-agent repeat --mode {t.mode} --target {t.target} --nth {t.n} "
                        f"--count {REPEAT}{exp}{flt} --out $OUT/test_{t.tid}.log")
        body += ["kml_scan", f"cat $D/kmemleak > $OUT/round_{i}.txt", "echo clear > $D/kmemleak"]
        # A round that was started but never finished crashed the guest:
        # record it and move on instead of crashing again.
        job.append(f"if [ -f $OUT/start_round_{i} ] && [ ! -f $OUT/done_round_{i} ]; then\n"
                   f"  echo crashed > $OUT/crashed_round_{i}; touch $OUT/done_round_{i}\nfi")
        job.append(f"if [ ! -f $OUT/done_round_{i} ]; then\n  " + "\n  ".join(body)
                   + f"\n  touch $OUT/done_round_{i}\nfi")
    return job


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------

KMALLOC_BUCKETS = [8, 16, 32, 64, 96, 128, 192, 256, 512, 1024, 2048, 4096, 8192]


def size_compatible(requested: int, reported: int) -> bool:
    """kmemleak reports the slab object size, i.e. the request rounded up."""
    if requested < 0:
        return False
    if reported == requested:
        return True
    bucket = next((b for b in KMALLOC_BUCKETS if b >= requested), None)
    return bucket is not None and requested <= reported <= bucket


@dataclass
class Verdict:
    id: str
    module: str
    status: str                  # confirmed | not-reproduced | inconclusive
    reason: str
    tests: list[dict] = field(default_factory=list)


def _leaks_for(test: Test, leaks: list[evidence.LeakObject], alone: bool) -> list[evidence.LeakObject]:
    out = []
    for lk in leaks:
        if test.module in lk.modules():
            out.append(lk)
        elif alone and lk.unresolved_module_frames and lk.comm == "klg-agent":
            out.append(lk)
    return out


def _leak_record(lk: evidence.LeakObject, module: str) -> dict:
    locs, funcs = evidence.module_frame_info(lk.frames, module)
    return {"size": lk.size, "locs": [list(l) for l in locs], "functions": funcs,
            "resolved": module in lk.modules(),
            "backtrace": [fr.text + (f" [{fr.module}]" if fr.module else "")
                          for fr in lk.frames][:8]}


def judge(candidates: list[dict], plan: dict[str, dict], rounds: list[list[Test]],
          out_dir: Path, reports: dict[str, dict]) -> list[Verdict]:
    by_cand: dict[str, list[dict]] = {}
    control: dict[str, list[dict]] = {}
    crashed: dict[str, str] = {}
    symmap = evidence.SymbolMap.from_logs(sorted(out_dir.glob("*.log")))
    for i, rnd in enumerate(rounds):
        report = out_dir / f"round_{i}.txt"
        leaks = evidence.parse_kmemleak(report.read_text(errors="replace") if report.exists() else "")
        for lk in leaks:
            if lk.raw_addresses:
                lk.resolve(symmap, {t.module for t in rnd})
        if (out_dir / f"crashed_round_{i}").exists():
            for t in rnd:
                for cid in t.candidates:
                    crashed[cid] = t.tid
        for t in rnd:
            mine = [_leak_record(lk, t.module) for lk in _leaks_for(t, leaks, alone=len(rnd) == 1)]
            log = out_dir / f"test_{t.tid}.log"
            attempts = evidence.parse_agent_log(log)
            if t.n == 0:
                control[t.module] = mine
                continue
            if t.expect:
                hits = [a for a in attempts if a.injected and
                        any(fr.text == t.expect for fr in a.fault_frames())]
            else:  # silent fault: count attempts where it fired and the routine failed
                hits = [a for a in attempts if a.injected and a.ret < 0]
            rec = {"test": t.tid, "fail_nth": t.n, "expected_frame": t.expect,
                   "attempts": len(attempts), "fault_hits": len(hits),
                   "missed": log.exists() and "@@MISS" in log.read_text(errors="replace"),
                   "returns": sorted({a.ret if a.ret >= 0 else -a.errno for a in hits}),
                   "leaks": mine}
            for cid in t.candidates:
                by_cand.setdefault(cid, []).append(rec)

    verdicts = []
    for c in candidates:
        cid, mod = c["id"], c["module"]
        p = plan.get(cid, {})
        if p.get("status") != "planned":
            verdicts.append(Verdict(cid, mod, "inconclusive", p.get("reason", "not planned")))
            continue
        recs = by_cand.get(cid, [])
        want = evidence.loc_of(c["alloc"])
        size = c.get("alloc_size", -1)
        only_site = evidence.single_site(reports.get(mod, {}).get("alloc_sites", {}), c["function"])
        confirmed, injected = None, False
        for r in recs:
            if r["fault_hits"]:
                injected = True
            how = (f"failing {r['expected_frame']}" if r["expected_frame"]
                   else f"a silent fault at fail-nth={r['fail_nth']}")
            for lk in r["leaks"]:
                locs = [tuple(l) for l in lk["locs"]]
                if want in locs:
                    confirmed = f"leak at {want[0]}:{want[1]} after {how}"
                elif c["function"] in lk["functions"] and only_site == want and r["fault_hits"]:
                    confirmed = (f"leak in {c['function']}() after {how}; frame has no line "
                                 f"info (merged by optimisation), function's only allocation "
                                 f"site is line {want[1]}")
                elif not lk["resolved"] and r["fault_hits"] and size_compatible(size, lk["size"]):
                    confirmed = (f"leak of {lk['size']} bytes (requested {size}) after {how}; "
                                 f"module already unloaded, attributed by size")
            if confirmed:
                break
        ctrl = [lk for lk in control.get(mod, []) if list(want) in lk["locs"]]
        if confirmed:
            v = Verdict(cid, mod, "confirmed", confirmed, recs)
        elif ctrl:
            v = Verdict(cid, mod, "confirmed", "leaks even without fault injection", recs)
        elif cid in crashed and not injected:
            v = Verdict(cid, mod, "inconclusive",
                        f"the guest kernel crashed during test {crashed[cid]}", recs)
        elif injected:
            v = Verdict(cid, mod, "not-reproduced",
                        "predicted failure injected, no object left unreferenced", recs)
        else:
            v = Verdict(cid, mod, "inconclusive", "fault point not reproducible in confirmation run", recs)
        verdicts.append(v)
    return verdicts


# ---------------------------------------------------------------------------
# Leaks found by the sweeps (dynamic results)
# ---------------------------------------------------------------------------

def dynamic_sites(report: Path, mods: dict[str, dict],
                  gt: dict | None, reports: dict[str, dict]) -> list[dict]:
    """Allocation sites a purely dynamic tool would report from kmemleak.

    Each leaked object is attributed to one allocation site read off its
    backtrace, as an analyst would: with ground truth, a known leaking caller
    if one appears (allocation wrappers), otherwise the innermost module
    frame. Frames without line information fall back to the function's only
    allocation site. Per-module scans after init-mode sweeps are attributed
    using klg_modwatch's address log.
    """
    out = report.parent
    symmap = evidence.SymbolMap.from_logs(sorted(out.glob("*.log")))
    sources = [(report, None)]
    if report.name == "kmemleak_exhaustive.txt":
        sources += [(p, {p.stem.removeprefix("kmemleak_sweep_")})
                    for p in sorted(out.glob("kmemleak_sweep_*.txt"))]
    found: dict[tuple[str, str, int], dict] = {}
    for path, only in sources:
        if not path.exists():
            continue
        for lk in evidence.parse_kmemleak(path.read_text(errors="replace")):
            if lk.raw_addresses and only:
                lk.resolve(symmap, only)
            for mod in lk.modules():
                if mod not in mods:
                    continue
                locs, funcs = evidence.module_frame_info(lk.frames, mod)
                sites = reports.get(mod, {}).get("alloc_sites", {})
                for fn in funcs:
                    if (s := evidence.single_site(sites, fn)) is not None and s not in locs:
                        locs.append(s)
                if gt is not None:
                    known = [l for l in locs if l[0] == f"{mod}.c" and (mod, l[1]) in gt]
                    if not known:
                        continue
                    leaking = [l for l in known if gt[(mod, l[1])].label == "LEAK"]
                    site = leaking[0] if leaking else known[0]
                elif locs:
                    site = locs[0]                 # no ground truth: innermost frame
                else:
                    continue
                key = (mod, site[0], site[1])
                if key not in found:
                    found[key] = {"module": mod, "file": site[0], "line": site[1], "objects": 0,
                                  "size": lk.size,
                                  "backtrace": [fr.text + (f" [{fr.module}]" if fr.module else "")
                                                for fr in lk.frames][:10]}
                found[key]["objects"] += 1
    return [found[k] for k in sorted(found)]


def executions(log: Path) -> int:
    return len(evidence.parse_agent_log(log))


def crashes(share: Path) -> list[dict]:
    p = share / "out" / "crashes.json"
    return json.loads(p.read_text()) if p.exists() else []


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(mods: dict[str, dict], static_reports: dict[str, dict],
        src_dir: Path = config.CORPUS, out_root: Path = config.RUNTIME_DIR,
        skip_sweep: bool = False, baselines: bool = True,
        targets: list[Target] | None = None, gt=..., inject_fns: list[str] | None = None,
        resilient: bool = False) -> dict:
    """mods: {name: {"ko", "src"}}; static_reports: {name: analyser JSON}."""
    evidence.KO_PATHS.update({name: Path(m["ko"]) for name, m in mods.items()})
    targets = targets or [Target.of(name, m["src"]) for name, m in sorted(mods.items())]
    tmap = {t.module: t for t in targets}
    if gt is ...:
        gt = ground_truth.load(src_dir)
    if inject_fns is None:
        inject_fns = error_injectable(src_dir)
    timing = {}
    out_root.mkdir(parents=True, exist_ok=True)

    base_out = out_root / "sweep" / "out"
    map_out = out_root / "mapping" / "out"
    if not skip_sweep:
        if baselines:
            _write_share(out_root / "sweep", mods, sweep_job(targets, inject_fns))
            timing["sweep_vm_s"] = _run_vm(out_root / "sweep", resilient=resilient)
        _write_share(out_root / "mapping", mods, mapping_job(targets, inject_fns))
        timing["mapping_vm_s"] = _run_vm(out_root / "mapping", resilient=resilient)

    fmaps = {t.module: fault_map(t.module, map_out / f"sweep_{t.module}.log") for t in targets}
    candidates = [c for rep in static_reports.values() for c in rep["candidates"]]
    tests, plan = plan_tests(candidates, fmaps, tmap, static_reports)
    rounds = schedule(tests)

    confirm_share = out_root / "confirm"
    _write_share(confirm_share, mods, confirm_job(rounds, targets, inject_fns))
    timing["confirm_vm_s"] = _run_vm(confirm_share, resilient=resilient)
    verdicts = judge(candidates, plan, rounds, confirm_share / "out", static_reports)

    map_exec = sum(executions(map_out / f"sweep_{t.module}.log") for t in targets)
    conf_exec = sum(executions(confirm_share / "out" / f"test_{t.tid}.log") for r in rounds for t in r)
    result = {
        "verdicts": [asdict(v) for v in verdicts],
        "fault_points": {m: [asdict(fp) for fp in fps] for m, fps in fmaps.items()},
        "rounds": [[t.tid for t in r] for r in rounds],
        # Leaks the module-filtered sweep itself left behind (no static
        # warning needed); part of KernelLeakGuard's combined output.
        "sweep_leaks": dynamic_sites(map_out / "kmemleak_exhaustive.txt", mods, gt, static_reports),
        "hybrid_executions": map_exec + conf_exec,
        "mapping_executions": map_exec,
        "confirm_executions": conf_exec,
        "kmemleak_rounds": len(rounds),
        "crashes": {"mapping": crashes(out_root / "mapping"), "confirm": crashes(confirm_share)},
        "timing": timing,
    }
    if baselines and (base_out / "kmemleak_exhaustive.txt").exists():
        result["crashes"]["baseline"] = crashes(out_root / "sweep")
        result["baselines"] = {
            "exhaustive": {
                "sites": dynamic_sites(base_out / "kmemleak_exhaustive.txt", mods, gt, static_reports),
                "executions": sum(executions(base_out / f"sweep_{t.module}.log") for t in targets),
            },
            "random": {
                "sites": dynamic_sites(base_out / "kmemleak_random.txt", mods, gt, static_reports),
                "executions": sum(executions(base_out / f"random_{t.module}.log") for t in targets),
                "probability": RANDOM_PROBABILITY,
                "budget_per_module": RANDOM_BUDGET,
            },
        }
    (out_root / "verification.json").write_text(json.dumps(result, indent=2))
    return result
