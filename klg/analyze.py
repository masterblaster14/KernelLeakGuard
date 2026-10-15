"""Run the static analyser (klg-analyze) over the corpus."""
import json
import subprocess
from pathlib import Path

from . import config

# Analyser configurations used in the evaluation (ablation study).
VARIANTS = {
    "full": [],
    "no-escape": ["--no-escape"],
    "no-interproc": ["--no-interproc"],
    "no-corr": ["--no-corr"],
    "no-containers": ["--no-containers"],
    "naive": ["--naive"],
}


def analyze_module(bc: Path, module: str, variant: str = "full",
                   out_dir: Path = config.STATIC_DIR) -> dict:
    out = out_dir / variant / f"{module}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(config.ANALYZER), str(bc), "-o", str(out), "--module-name", module,
           *VARIANTS[variant]]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"klg-analyze failed on {bc}: {res.stderr}")
    return json.loads(out.read_text())


def analyze_all(modules: dict[str, dict], variant: str = "full") -> dict[str, dict]:
    return {name: analyze_module(m["bc"], name, variant) for name, m in modules.items()}


def load_reports(variant: str = "full") -> dict[str, dict]:
    d = config.STATIC_DIR / variant
    return {p.stem: json.loads(p.read_text()) for p in sorted(d.glob("*.json"))}
