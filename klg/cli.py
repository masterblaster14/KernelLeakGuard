"""KernelLeakGuard command line interface.

    python3 -m klg build       build corpus modules and LLVM IR
    python3 -m klg analyze     run the static analyser (all variants)
    python3 -m klg verify      runtime verification in the QEMU guest
    python3 -m klg evaluate    metrics against ground truth
    python3 -m klg all         everything above
    python3 -m klg show        print the latest findings
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from . import analyze, build, config, evaluate, verify


def _modules():
    mods = {}
    for ko in sorted(config.CORPUS.glob("klg_*.ko")):
        bc = config.IR_DIR / f"{ko.stem}.bc"
        mods[ko.stem] = {"ko": ko, "bc": bc, "src": ko.with_suffix(".c")}
    if not mods:
        sys.exit("no modules built yet: run `python3 -m klg build` first")
    return mods


def cmd_build(args):
    t = time.time()
    mods = build.build_all()
    print(f"[klg] built {len(mods)} modules and their LLVM IR in {time.time() - t:.1f}s")


def cmd_analyze(args):
    mods = _modules()
    variants = list(analyze.VARIANTS) if args.all_variants else ["full"]
    for v in variants:
        reps = analyze.analyze_all(mods, v)
        n = sum(len(r["candidates"]) for r in reps.values())
        print(f"[klg] static ({v}): {n} warnings in {len(reps)} modules")


def cmd_verify(args):
    mods = _modules()
    reps = analyze.load_reports("full")
    res = verify.run(mods, reps, skip_sweep=args.skip_sweep)
    counts = {}
    for v in res["verdicts"]:
        counts[v["status"]] = counts.get(v["status"], 0) + 1
    print(f"[klg] runtime verification: {counts}  timing={res['timing']}")


def cmd_evaluate(args):
    ev = evaluate.evaluate()
    print(evaluate.summary_table(ev))
    if "triage" in ev:
        print("\nTriage of static warnings (verdict -> ground truth):")
        for status, d in ev["triage"].items():
            print(f"  {status:15s} {d}")


def cmd_show(args):
    reps = analyze.load_reports("full")
    ver = {}
    vf = config.RUNTIME_DIR / "verification.json"
    if vf.exists():
        ver = {v["id"]: v for v in json.loads(vf.read_text())["verdicts"]}
    for r in reps.values():
        for c in r["candidates"]:
            v = ver.get(c["id"], {})
            print(f"{c['module']}:{c['alloc']['line']} {c['function']}() "
                  f"{c['allocator']} leaks at line {c['exit']['line']} "
                  f"({c['return_value']}, {c['confidence']}) -> {v.get('status', 'unverified')}")
            if v.get("reason"):
                print(f"    {v['reason']}")


def cmd_fix(args):
    from . import fix
    res = fix.generate_and_validate(run_vm=not args.no_vm)
    for r in res:
        ch = r["checks"]
        print(f"{r['module']:28s} {r['status']:10s} compiles={ch.get('compiles')} "
              f"static_clean={ch.get('static_clean')} runtime_clean={ch.get('runtime_clean')} "
              f"faults={ch.get('runtime_faults_exercised')}  {r['reason']}")
    ok = sum(1 for r in res if r["status"] == "validated")
    rt = sum(1 for r in res if r["status"] == "runtime-validated")
    print(f"[klg] fix patches: {ok} fully validated, {rt} runtime-validated only, of "
          f"{len(res)} confirmed leaks (patches in results/fixes/patches)")


def cmd_real(args):
    from . import real
    real.run(skip_build=args.skip_build, skip_vm=args.skip_vm,
             only=args.only.split(",") if args.only else None)


def cmd_seed(args):
    from . import seed
    seed.run(only=args.only.split(",") if args.only else None, skip_vm=args.skip_vm)


def cmd_all(args):
    cmd_build(args)
    args.all_variants = True
    cmd_analyze(args)
    args.skip_sweep = False
    cmd_verify(args)
    cmd_evaluate(args)


def main(argv=None):
    p = argparse.ArgumentParser(prog="klg", description="KernelLeakGuard")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build").set_defaults(fn=cmd_build)
    a = sub.add_parser("analyze")
    a.add_argument("--all-variants", action="store_true", help="also run ablation variants")
    a.set_defaults(fn=cmd_analyze)
    v = sub.add_parser("verify")
    v.add_argument("--skip-sweep", action="store_true", help="reuse the previous sweep run")
    v.set_defaults(fn=cmd_verify)
    sub.add_parser("evaluate").set_defaults(fn=cmd_evaluate)
    f = sub.add_parser("fix", help="generate and validate fix patches for confirmed leaks")
    f.add_argument("--no-vm", action="store_true", help="skip the runtime validation")
    f.set_defaults(fn=cmd_fix)
    r = sub.add_parser("real", help="analyse and verify real Linux kernel modules")
    r.add_argument("--skip-build", action="store_true")
    r.add_argument("--skip-vm", action="store_true")
    r.add_argument("--only", help="comma-separated module names (testing)")
    r.set_defaults(fn=cmd_real)
    sd = sub.add_parser("seed", help="seed known leaks into real kernel modules and verify them")
    sd.add_argument("--only", help="comma-separated seed names")
    sd.add_argument("--skip-vm", action="store_true")
    sd.set_defaults(fn=cmd_seed)
    sub.add_parser("show").set_defaults(fn=cmd_show)
    sub.add_parser("all").set_defaults(fn=cmd_all)
    args = p.parse_args(argv)
    config.ensure_dirs()
    args.fn(args)


if __name__ == "__main__":
    main()
