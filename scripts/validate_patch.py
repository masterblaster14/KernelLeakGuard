"""Statically validate a kernel patch on a real module, the way `klg fix`
validates fixes: the patched module must compile and the analyser's warning
must disappear without new ones.

    python3 scripts/validate_patch.py MODULE DIR FILE PATCHED_FILE OUT_DIR
    e.g. ntfs3 fs/ntfs3 fslog.c /path/to/patched/fslog.c results/real/ntfs3_fix
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from klg import config, seed  # noqa: E402

mod, d, fname, patched, out = sys.argv[1:6]
out = Path(out).resolve()
res = {}
for tag, src in (("original", config.KSRC / d / fname), ("patched", Path(patched))):
    work = out / tag
    ko = seed._build_module(mod, src, work, d, fname)
    rep = seed._analyze(mod, ko, work, tag)
    res[tag] = sorted((c["function"], c["alloc"]["line"], c["exit"]["line"], c["confidence"])
                      for c in rep["candidates"])
gone = [w for w in res["original"] if w not in res["patched"]]
new = [w for w in res["patched"] if w not in res["original"]]
summary = {"module": mod, "file": f"{d}/{fname}", "compiles": True,
           "warnings_original": len(res["original"]), "warnings_patched": len(res["patched"]),
           "removed": gone, "added": new}
(out / "validation.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
