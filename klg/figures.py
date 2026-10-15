"""Figures for the report and presentation (matplotlib, PNG at 200 dpi).

    .venv/bin/python -m klg.figures

Colours follow a validated categorical palette (slot 1 blue, slot 2 orange)
with recessive grid and axes; values are labelled directly on the bars.
"""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

from . import config  # noqa: E402

BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, INK2, MUTED, GRID, BASE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
FIG_DIR = config.ROOT / "docs" / "figures"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": BASE,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlecolor": INK,
    "legend.frameon": False,
})

LABELS = {
    "cppcheck": "cppcheck", "static/naive": "Static\n(naive)", "static/full": "Static\n(KLG)",
    "hybrid": "Hybrid\n(confirmed)", "klg/combined": "KLG\n(complete)",
    "dynamic/exhaustive": "Dynamic\nexhaustive", "dynamic/random": "Dynamic\nrandom",
}


def _save(fig, name):
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIG_DIR / name, dpi=200, facecolor="white")
    plt.close(fig)


def _label_bars(ax, bars, fmt="{:.2f}"):
    for b in bars:
        h = b.get_height()
        ax.annotate(fmt.format(h), (b.get_x() + b.get_width() / 2, h), xytext=(0, 3),
                    textcoords="offset points", ha="center", va="bottom", fontsize=8, color=INK2)


def precision_recall(ev):
    names = [n for n in LABELS if n in ev["approaches"]]
    prec = [ev["approaches"][n]["precision"] for n in names]
    rec = [ev["approaches"][n]["recall"] for n in names]
    fig, ax = plt.subplots(figsize=(9.5, 4))
    x = range(len(names))
    w = 0.36
    b1 = ax.bar([i - w / 2 - 0.01 for i in x], prec, w, color=BLUE, label="Precision")
    b2 = ax.bar([i + w / 2 + 0.01 for i in x], rec, w, color=ORANGE, label="Recall")
    _label_bars(ax, b1)
    _label_bars(ax, b2)
    ax.set_xticks(list(x), [LABELS[n] for n in names])
    ax.set_ylim(0, 1.12)
    ax.set_title("Precision and recall per approach (per allocation site)")
    ax.legend(loc="upper left", ncol=2)
    _save(fig, "fig_precision_recall.png")


def ablation(ev):
    order = ["static/naive", "static/no-escape", "static/no-interproc", "static/no-containers",
             "static/no-corr", "static/full"]
    label = {"static/naive": "naive (all off)", "static/no-escape": "no ownership\ntransfer",
             "static/no-interproc": "no function\nsummaries", "static/no-containers": "no stack\nobjects",
             "static/no-corr": "no branch\ncorrelation", "static/full": "full analysis"}
    names = [n for n in order if n in ev["approaches"]]
    f1 = [ev["approaches"][n]["f1"] for n in names]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    bars = ax.bar(range(len(names)), f1, 0.6, color=BLUE)
    _label_bars(ax, bars)
    ax.set_xticks(range(len(names)), [label[n] for n in names])
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("F1 score")
    ax.set_title("Ablation: contribution of each analysis refinement")
    _save(fig, "fig_ablation.png")


def warnings_breakdown(ev):
    order = ["static/naive", "static/no-escape", "static/no-interproc", "static/no-containers",
             "static/no-corr", "static/full"]
    names = [n for n in order if n in ev["approaches"]]
    tp = [ev["approaches"][n]["tp"] for n in names]
    fp = [ev["approaches"][n]["fp"] for n in names]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    x = range(len(names))
    b1 = ax.bar(x, tp, 0.6, color=BLUE, label="true leak sites reported")
    b2 = ax.bar(x, fp, 0.6, bottom=tp, color=ORANGE, label="safe sites reported (false alarms)",
                edgecolor="white", linewidth=1.5)
    for i in x:
        ax.annotate(f"{tp[i]} / {fp[i]}", (i, tp[i] + fp[i]), xytext=(0, 3), textcoords="offset points",
                    ha="center", fontsize=8, color=INK2)
    ax.set_xticks(list(x), [n.split("/")[1] for n in names])
    ax.set_ylabel("allocation sites")
    gt = ev["ground_truth"]
    ax.set_title(f"Static warnings: true vs false ({gt['leak_sites']} leaking, "
                 f"{gt['safe_sites']} safe sites)")
    ax.legend(loc="upper right")
    _save(fig, "fig_static_breakdown.png")


def triage(ev):
    if "triage" not in ev:
        return
    statuses = ["confirmed", "not-reproduced", "inconclusive"]
    leak = [ev["triage"].get(s, {}).get("LEAK", 0) for s in statuses]
    safe = [ev["triage"].get(s, {}).get("SAFE", 0) for s in statuses]
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    x = range(len(statuses))
    w = 0.36
    b1 = ax.bar([i - w / 2 - 0.01 for i in x], leak, w, color=BLUE, label="warning on a real leak")
    b2 = ax.bar([i + w / 2 + 0.01 for i in x], safe, w, color=ORANGE, label="warning on safe code")
    _label_bars(ax, b1, "{:.0f}")
    _label_bars(ax, b2, "{:.0f}")
    ax.set_xticks(list(x), statuses)
    ax.set_ylabel("static warnings")
    ax.set_title("Runtime verdicts for the static warnings")
    ax.legend(loc="upper right")
    _save(fig, "fig_triage.png")


def cost(ev):
    names = [n for n in ("klg/combined", "dynamic/exhaustive", "dynamic/random") if n in ev["approaches"]]
    ex = [ev["approaches"][n].get("executions", 0) for n in names]
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    bars = ax.barh(range(len(names)), ex, 0.55, color=BLUE)
    for b, v in zip(bars, ex):
        ax.annotate(f"{v}", (v, b.get_y() + b.get_height() / 2), xytext=(4, 0),
                    textcoords="offset points", va="center", fontsize=9, color=INK2)
    ax.set_yticks(range(len(names)), [LABELS[n].replace("\n", " ") for n in names])
    ax.invert_yaxis()
    ax.set_xlabel("executions of kernel routines under fault injection")
    ax.set_title("Runtime cost of verification")
    ax.grid(axis="y", visible=False)
    _save(fig, "fig_cost.png")


def _box(ax, x, y, w, h, title, body, color):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                facecolor="white", edgecolor=color, linewidth=1.6))
    ax.text(x + w / 2, y + h - 0.16, title, ha="center", va="top", fontsize=10,
            fontweight="bold", color=INK)
    ax.text(x + w / 2, y + h - 0.48, body, ha="center", va="top", fontsize=7.6, color=INK2,
            linespacing=1.35)


def _arrow(ax, a, b):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=12, color=MUTED,
                                 linewidth=1.3))


def architecture():
    fig, ax = plt.subplots(figsize=(11, 5.6))
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 5.6)
    ax.axis("off")
    _box(ax, 0.2, 3.5, 2.3, 1.8, "Kernel module C", "benchmark corpus\n(32 modules)\nor real driver code", MUTED)
    _box(ax, 3.0, 3.5, 2.3, 1.8, "IR generation", "kbuild command\n+ clang -emit-llvm\n(-O2 front end,\nno LLVM passes)", BLUE)
    _box(ax, 5.8, 3.5, 2.5, 1.8, "klg-analyze (C++)", "mem2reg, alias & escape\nfunction summaries\npath search to exits\nbranch correlation", BLUE)
    _box(ax, 8.7, 3.5, 2.1, 1.8, "Candidates", "alloc site, exit,\nreturn value,\ntrigger calls,\nconfidence (JSON)", BLUE)
    ax.add_patch(FancyBboxPatch((0.2, 0.25), 8.1, 2.7, boxstyle="round,pad=0.02,rounding_size=0.1",
                                facecolor="#f9f9f7", edgecolor=BASE, linewidth=1.0, linestyle="--"))
    ax.text(0.4, 2.78, "QEMU/KVM guest: Linux 6.18.55 + kmemleak + fault injection", fontsize=8.5,
            color=INK2, va="top")
    _box(ax, 0.5, 0.45, 2.3, 1.95, "1. Fault-point sweep", "klg-agent sets fail-nth\n= 1, 2, 3 ...\nstack trace of each\ninjected fault", ORANGE)
    _box(ax, 3.1, 0.45, 2.3, 1.95, "2. Targeted injection", "fail the candidate's\ntrigger call (×3);\nfailslab, fail_function,\nfail_usercopy", ORANGE)
    _box(ax, 5.7, 0.45, 2.3, 1.95, "3. Kmemleak", "scan ×2 after 6 s;\nunreferenced objects\nwith allocation\nbacktraces", ORANGE)
    _box(ax, 8.7, 0.45, 2.1, 2.5, "Verdicts", "faddr2line → source\nline; attribution\n\nconfirmed\nnot reproduced\ninconclusive\n+ evidence, dashboard", BLUE)
    _arrow(ax, (2.5, 4.4), (3.0, 4.4))
    _arrow(ax, (5.3, 4.4), (5.8, 4.4))
    _arrow(ax, (8.3, 4.4), (8.7, 4.4))
    _arrow(ax, (9.75, 3.5), (7.0, 2.42))
    _arrow(ax, (2.8, 1.4), (3.1, 1.4))
    _arrow(ax, (5.4, 1.4), (5.7, 1.4))
    _arrow(ax, (8.0, 1.4), (8.7, 1.4))
    ax.text(8.6, 3.05, "trigger lines", fontsize=7.5, color=MUTED, ha="right")
    _save(fig, "fig_architecture.png")


def _node(ax, x, y, w, h, label, kind="box", color=BLUE):
    if kind == "diamond":
        from matplotlib.patches import Polygon
        ax.add_patch(Polygon([(x, y + h / 2), (x + w / 2, y + h), (x + w, y + h / 2), (x + w / 2, y)],
                             closed=True, facecolor="white", edgecolor=color, linewidth=1.5))
    else:
        style = "round,pad=0.02,rounding_size=0.25" if kind == "terminal" else "round,pad=0.02,rounding_size=0.06"
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=style, facecolor="white",
                                    edgecolor=color, linewidth=1.5))
    ax.text(x + w / 2, y + h / 2, label, ha="center", va="center", fontsize=8.3, color=INK,
            linespacing=1.25)


def flowchart():
    """Flowchart of runtime verification for one candidate."""
    fig, ax = plt.subplots(figsize=(8.5, 10.5))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 13)
    ax.axis("off")
    cx = 3.2
    steps = [
        (12.0, "terminal", "Static candidate C\n(alloc line, trigger lines, function)"),
        (10.6, "box", "Sweep: fail-nth = 1, 2, 3 ...\nrecord stack of every injected fault"),
        (9.2, "box", "Symbolise frames (faddr2line)\n→ map fault number N → source line"),
        (7.6, "diamond", "Some N fails a\ntrigger call of C?"),
        (6.0, "box", "Inject N three times;\ncheck fault hit the expected frame"),
        (4.6, "box", "Wait 6 s, scan kmemleak twice;\nattribute objects by backtrace / size"),
        (3.0, "diamond", "Object allocated at\nC's alloc site leaked?"),
    ]
    w = 4.4
    ys = {}
    for y, kind, label in steps:
        h = 1.3 if kind == "diamond" else 0.9
        _node(ax, cx - w / 2, y - h / 2, w, h, label, kind, BLUE if kind != "terminal" else MUTED)
        ys[label] = (y, h)
    order = [s[0] for s in steps]
    for a, b in zip(order, order[1:]):
        ha = 0.65 if a in (7.6, 3.0) else 0.45
        hb = 0.65 if b in (7.6, 3.0) else 0.45
        _arrow(ax, (cx, a - ha), (cx, b + hb))
    _node(ax, 6.6, 7.6 - 0.45, 3.0, 0.9, "INCONCLUSIVE\n(failure not injectable)", "terminal", MUTED)
    _arrow(ax, (cx + 2.2, 7.6), (6.6, 7.6))
    ax.text(5.6, 7.75, "no", fontsize=8, color=INK2)
    ax.text(cx + 0.12, 6.75, "yes", fontsize=8, color=INK2)
    _node(ax, cx - 1.6, 1.0, 3.2, 0.9, "CONFIRMED\n+ evidence, reproduction", "terminal", BLUE)
    _arrow(ax, (cx, 3.0 - 0.65), (cx, 1.9))
    ax.text(cx + 0.12, 2.1, "yes", fontsize=8, color=INK2)
    _node(ax, 6.6, 3.0 - 0.45, 3.0, 0.9, "NOT REPRODUCED\n(likely false positive)", "terminal", ORANGE)
    _arrow(ax, (cx + 2.2, 3.0), (6.6, 3.0))
    ax.text(5.6, 3.15, "no", fontsize=8, color=INK2)
    ax.set_title("Flowchart of runtime verification", fontsize=12)
    _save(fig, "fig_flowchart.png")


def terminal(name, title, lines, width=10.5):
    """Render captured command output as a terminal-style image."""
    h = 0.6 + 0.22 * len(lines)
    fig, ax = plt.subplots(figsize=(width, h))
    fig.patch.set_facecolor("#1a1a19")
    ax.set_facecolor("#1a1a19")
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, len(lines) + 1.5)
    ax.text(0.01, len(lines) + 0.9, title, color="#c3c2b7", fontsize=9, family="DejaVu Sans Mono",
            va="center")
    for i, line in enumerate(lines):
        color = "#f0efec"
        if line.startswith("$"):
            color = "#86b6ef"
        elif "confirmed" in line or "CONFIRMED" in line:
            color = "#86e08a"
        elif "not-reproduced" in line or "inconclusive" in line:
            color = "#f0b08a"
        ax.text(0.01, len(lines) - i, line[:150], color=color, fontsize=8.2,
                family="DejaVu Sans Mono", va="center")
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / name, dpi=170, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)


def screenshots():
    log = config.RESULTS / "pipeline_demo.log"
    if log.exists():
        lines = [l.rstrip() for l in log.read_text().splitlines() if l.strip()]
        terminal("shot_pipeline.png", "Ubuntu (WSL2) — python3 -m klg all", lines[:40])
    show = config.RESULTS / "show_demo.log"
    if show.exists():
        lines = [l.rstrip() for l in show.read_text().splitlines()]
        terminal("shot_findings.png", "Ubuntu (WSL2) — python3 -m klg show", lines[:40], 13)
    ag = sorted((config.RUNTIME_DIR / "confirm" / "out").glob("test_klg_l03*__n*.log"))
    if ag:
        raw = ag[0].read_text().splitlines()
        keep = [l for l in raw if l.startswith("@@") or "FAULT_INJECTION" in l
                or "[klg_" in l or "name fail" in l][:22]
        terminal("shot_agent.png", "klg-agent output inside the guest (fault injection)",
                 ["$ klg-agent repeat --mode trigger --target /sys/kernel/debug/klg_klg_l03_reg_fail "
                  "--nth 3 --count 3"] + keep)
    rounds = sorted((config.RUNTIME_DIR / "confirm" / "out").glob("round_*.txt"))
    for r in rounds:
        text = r.read_text()
        if "klg_l03_reg_fail" in text:
            blk = text.split("unreferenced object")
            pick = next(("unreferenced object" + b for b in blk[1:] if "klg_l03" in b), "")
            terminal("shot_kmemleak.png", "cat /sys/kernel/debug/kmemleak (guest)",
                     ["$ cat /sys/kernel/debug/kmemleak"] + pick.splitlines()[:16])
            break


def main():
    flowchart()
    screenshots()
    ev = json.loads((config.RESULTS / "evaluation.json").read_text())
    precision_recall(ev)
    ablation(ev)
    warnings_breakdown(ev)
    triage(ev)
    cost(ev)
    architecture()
    print(f"figures written to {FIG_DIR}")


if __name__ == "__main__":
    main()
