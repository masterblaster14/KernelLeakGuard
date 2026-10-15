"""Ground truth for the benchmark corpus, read from source annotations.

Every allocation site in the corpus carries a trailing comment:
    /* GT:LEAK */  the allocation leaks on at least one path
    /* GT:SAFE */  the allocation is always released or handed over
"""
import re
from dataclasses import dataclass
from pathlib import Path

from . import config

_MARK = re.compile(r"/\*\s*GT:(LEAK|SAFE)\s*\*/")


@dataclass(frozen=True)
class Site:
    module: str
    file: str
    line: int
    label: str  # "LEAK" or "SAFE"
    code: str


def sites_for(src: Path) -> list[Site]:
    out = []
    for no, text in enumerate(src.read_text().splitlines(), start=1):
        m = _MARK.search(text)
        if m:
            out.append(Site(src.stem, src.name, no, m.group(1), text.strip()))
    return out


def load(src_dir: Path = config.CORPUS) -> dict[tuple[str, int], Site]:
    """Map (module, line) -> Site for all annotated allocation sites."""
    gt = {}
    for src in sorted(src_dir.glob("klg_*.c")):
        for s in sites_for(src):
            gt[(s.module, s.line)] = s
    return gt


def init_mode(src: Path) -> bool:
    """Modules without a debugfs trigger run their code in module_init."""
    return "KLG_TRIGGER" not in src.read_text()
