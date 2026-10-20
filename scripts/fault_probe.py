"""Probe a real module's init at chosen fault points (root-cause helper).

Runs MODULE's init once per fail-nth value (module-filtered numbering, as in
the mapping sweep), in batches, with one kmemleak scan and a dmesg capture per
batch. PROBE_KBUILD in the environment boots another guest kernel build
(modules still come from the main build); PROBE_KO probes another build of
the module itself.

    python3 scripts/fault_probe.py MODULE LO HI BATCH OUT_DIR
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from klg import config, real, verify  # noqa: E402
import os  # noqa: E402

if os.environ.get("PROBE_KBUILD"):
    os.environ["KBUILD"] = os.environ["PROBE_KBUILD"]   # read by vm/env.sh only

mod = sys.argv[1]
lo, hi, step = (int(x) for x in sys.argv[2:5])
share = Path(sys.argv[5]).resolve()
mods = real.built_modules()
verify.PRELOAD.clear()
verify.PRELOAD.update({d: mods[d] for d in real.load_order([mod], mods)})
t = verify.Target(mod, "init", f"/mnt/host/mods/{mod}.ko")
job = verify._job_setup([t], [])
for b in range(lo, hi + 1, step):
    e = min(b + step - 1, hi)
    # A batch that started but never finished crashed the guest: record, move on.
    job.append(f"if [ -f $OUT/started_{b} ] && [ ! -f $OUT/done_{b} ]; then "
               f"echo crashed > $OUT/crashed_{b}; touch $OUT/done_{b}; fi")
    job.append(f"if [ ! -f $OUT/done_{b} ]; then")
    job.append(f"  touch $OUT/started_{b}")
    job.append(f"  for n in $(seq {b} {e}); do klg-agent repeat --mode init --target {t.path} "
               f"--nth $n --count 1 --filter {mod} --out $OUT/run_{b}.log; done")
    job.append(f"  kml_scan; cat $D/kmemleak > $OUT/kml_{b}_{e}.txt; echo clear > $D/kmemleak")
    job.append(f"  dmesg > $OUT/dmesg_{b}.txt")
    job.append(f"  touch $OUT/done_{b}")
    job.append("fi")
# PROBE_KO: probe another build of the module (e.g. one with a candidate fix).
ko = Path(os.environ["PROBE_KO"]) if os.environ.get("PROBE_KO") else mods[mod]
verify._write_share(share, {mod: {"ko": ko}}, job)
secs = verify._run_vm(share, timeout=3600, resilient=True,
                      extra_cmdline=os.environ.get("PROBE_CMDLINE", ""))
print(f"vm {secs:.0f}s")
for f in sorted((share / "out").glob("kml_*.txt"), key=lambda p: int(p.stem.split("_")[1])):
    txt = f.read_text(errors="replace")
    print(f.stem, txt.count("unreferenced object"))
