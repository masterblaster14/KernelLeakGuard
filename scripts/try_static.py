"""Developer check: build IR for the corpus and print static findings vs ground truth."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from klg import analyze, build, config, ground_truth  # noqa: E402

variant = sys.argv[1] if len(sys.argv) > 1 else "full"
config.ensure_dirs()
gt = ground_truth.load()
mods = {}
for ko in sorted(config.CORPUS.glob("klg_*.ko")):
    mods[ko.stem] = {"bc": build.emit_ir(ko.with_suffix(".o"))}
reports = analyze.analyze_all(mods, variant)

flagged = set()
for name, rep in reports.items():
    for c in rep["candidates"]:
        flagged.add((name, c["alloc"]["line"]))
        trig = ",".join(f'{t["callee"]}@{t["line"]}' for t in c["triggers"]) or "-"
        print(f'{name:28s} {c["function"]:16s} alloc@{c["alloc"]["line"]:<3} '
              f'exit@{c["exit"]["line"]:<3} {c["exit_kind"]:7s} {c["return_value"]:22s} '
              f'{c["confidence"]:6s} trig={trig}')

tp = sum(1 for k, s in gt.items() if s.label == "LEAK" and k in flagged)
fn = [k for k, s in gt.items() if s.label == "LEAK" and k not in flagged]
fp = [k for k in flagged if k in gt and gt[k].label == "SAFE"]
unk = [k for k in flagged if k not in gt]
print(f"\n[{variant}] TP={tp} FN={len(fn)} FP={len(fp)} unannotated={len(unk)}")
print("FN:", fn)
print("FP:", fp)
print("unannotated:", unk)
