"""Filesystem layout shared by all KernelLeakGuard components."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KVER = os.environ.get("KVER", "6.18.55")
WORK = Path(os.environ.get("KLG_WORK", Path.home() / "klg-build"))
KSRC = Path(os.environ.get("KSRC", WORK / f"linux-{KVER}"))
KBUILD = Path(os.environ.get("KBUILD", WORK / "kbuild"))

CORPUS = ROOT / "corpus"
ANALYZER = ROOT / "analyzer" / "build" / "klg-analyze"
RESULTS = ROOT / "results"
IR_DIR = RESULTS / "ir"
STATIC_DIR = RESULTS / "static"
RUNTIME_DIR = RESULTS / "runtime"

FADDR2LINE = KSRC / "scripts" / "faddr2line"


def ensure_dirs():
    for d in (RESULTS, IR_DIR, STATIC_DIR, RUNTIME_DIR):
        d.mkdir(parents=True, exist_ok=True)
