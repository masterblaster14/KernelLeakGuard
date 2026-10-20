"""After a static-only refresh: re-plan the real-module warnings whose static
details changed, with the verifier's own planning on the recorded fault maps.
A warning that would need a new VM test is reported, not judged."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from klg import config, verify  # noqa: E402

REAL = config.RESULTS / "real"
ver_file = REAL / "runtime" / "verification.json"
ver = json.loads(ver_file.read_text())
reports = {p.stem: json.loads(p.read_text()) for p in (REAL / "static" / "full").glob("*.json")}
cands = {c["id"]: dict(c, module=m) for m, r in reports.items() for c in r["candidates"]}
old = {v["id"]: v for v in ver["verdicts"]}
assert set(cands) == set(old), "warning set changed: a full VM run is needed"
need_vm, changed = [], 0
for v in ver["verdicts"]:
    c = cands[v["id"]]
    m = c["module"]
    log = REAL / "runtime" / "mapping" / "out" / f"sweep_{m}.log"
    fmap = {m: verify.fault_map(m, log)} if log.exists() else {}
    targets = {m: verify.Target(m, "init", f"/mnt/host/mods/{m}.ko")}
    _, plan = verify.plan_tests([c], fmap, targets, reports)
    p = plan[c["id"]]
    if p["status"] == "planned":
        if not v["tests"]:
            need_vm.append(c["id"])
        continue
    if v["status"] != p["status"] or v["reason"] != p["reason"]:
        print(f"{c['id']}: {v['status']} ({v['reason']}) -> {p['status']} ({p['reason']})")
        v["status"], v["reason"] = p["status"], p["reason"]
        changed += 1
if need_vm:
    sys.exit(f"needs a VM test: {need_vm}")
ver_file.write_text(json.dumps(ver, indent=2))
print(f"re-planned; {changed} verdict reason(s) updated")
