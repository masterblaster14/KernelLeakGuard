"""KernelLeakGuard dashboard (Streamlit).

    .venv/bin/streamlit run dashboard/app.py      →  http://localhost:8501

Pages: overview, findings (source + runtime evidence), verified fix patches,
real-kernel results, evaluation, and a pipeline runner. The runner starts the
pipeline as a separate background process whose log is shown live, so a run
keeps going when the page reruns or the browser is reloaded.
"""
from __future__ import annotations

import html
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from klg import config  # noqa: E402

SERIES = ["#2a78d6", "#eb6834"]          # validated categorical slots 1 and 2
STATUS = {"confirmed": ("✔", "#0ca30c"), "not-reproduced": ("✖", "#d03b3b"),
          "inconclusive": ("?", "#898781"), "unverified": ("·", "#898781")}
RUN_LOG = config.RESULTS / "dashboard_run.log"
RUN_STATE = config.RESULTS / "dashboard_run.json"
STEPS = {
    "all": "Complete pipeline: build → analyse → verify in VM → evaluate (~4 min)",
    "build": "Build corpus modules, LLVM IR, klg-agent and guest initramfs",
    "analyze": "Static analysis, all six analyser configurations",
    "verify": "Runtime verification in the QEMU/KVM guest (~3 min)",
    "evaluate": "Metrics against ground truth",
    "fix": "Generate fix patches and validate them (compile, re-analyse, VM)",
    "real": "Real Linux kernel modules: static + runtime (~30 min)",
    "seed": "Seeded leaks in real modules: detect → confirm in VM → fix (~5 min)",
}

st.set_page_config(page_title="KernelLeakGuard", page_icon="🛡️", layout="wide")


# ------------------------------------------------------------------ data ----
def _json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


@st.cache_data(ttl=5)
def load(base: str):
    base = Path(base)
    static = {p.stem: _json(p, {}) for p in sorted((base / "static" / "full").glob("*.json"))}
    return static, _json(base / "runtime" / "verification.json", {})


static, ver = load(str(config.RESULTS))
ev = _json(config.RESULTS / "evaluation.json", {})
fixes = _json(config.RESULTS / "fixes" / "fixes.json", [])
verdicts = {v["id"]: v for v in ver.get("verdicts", [])}
cands = [c for r in static.values() for c in r.get("candidates", [])]


# ------------------------------------------------------------- pipeline -----
def run_state() -> dict:
    stt = _json(RUN_STATE, {})
    pid = stt.get("pid")
    alive = False
    if pid:
        try:
            with open(f"/proc/{pid}/stat") as f:
                alive = f.read().split(")")[-1].split()[0] not in ("Z", "X")
        except OSError:
            alive = False
    stt["running"] = alive
    log = RUN_LOG.read_text(errors="replace") if RUN_LOG.exists() else ""
    stt["exit"] = None
    for line in log.splitlines()[::-1]:
        if line.startswith("@@EXIT "):
            stt["exit"] = int(line.split()[1])
            break
    stt["log"] = log
    return stt


def start_run(step: str):
    config.RESULTS.mkdir(parents=True, exist_ok=True)
    extra = " --all-variants" if step == "analyze" else ""
    cmd = (f'cd "{ROOT}" && "{sys.executable}" -u -m klg {step}{extra}; '
           f'echo "@@EXIT $?"')
    with open(RUN_LOG, "w") as log:
        log.write(f"$ python3 -m klg {step}{extra}\n")
        log.flush()
        # New session: the run survives page reruns and can be stopped as a group.
        proc = subprocess.Popen(["bash", "-c", cmd], stdout=log, stderr=subprocess.STDOUT,
                                cwd=ROOT, start_new_session=True)
    RUN_STATE.write_text(json.dumps({"pid": proc.pid, "step": step, "started": time.time()}))


def stop_run(pid: int):
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        pass
    subprocess.run(["pkill", "-f", "qemu-system-x86_64"], check=False)


# ------------------------------------------------------------- helpers ------
def source_view(src: Path, c: dict) -> str:
    lines = src.read_text(errors="replace").splitlines()
    alloc, exit_ = c["alloc"]["line"], c["exit"]["line"]
    trig = {t["line"] for t in c["triggers"]}
    path = set(c.get("path_lines", []))
    marks = [alloc, exit_, *trig]
    lo, hi = max(1, min(marks) - 4), min(len(lines), max(marks) + 4)
    rows = []
    for n in range(lo, hi + 1):
        tag, bg = "", ""
        if n == alloc:
            tag, bg = "alloc", "rgba(42,120,214,0.18)"
        elif n in trig:
            tag, bg = "fails", "rgba(235,104,52,0.18)"
        elif n == exit_:
            tag, bg = "exit", "rgba(208,59,59,0.18)"
        elif n in path:
            bg = "rgba(137,135,129,0.08)"
        rows.append(f"<tr style='background:{bg}'><td style='color:#898781;text-align:right;"
                    f"padding-right:8px'>{n}</td><td style='color:#52514e;width:44px'>{tag}</td>"
                    f"<td><pre style='margin:0'>{html.escape(lines[n - 1])}</pre></td></tr>")
    return ("<table style='font-family:monospace;font-size:13px;border-collapse:collapse;"
            "width:100%'>" + "".join(rows) + "</table>")


def finding_table(cands, verdicts):
    rows = []
    for c in cands:
        status = verdicts.get(c["id"], {}).get("status", "unverified")
        rows.append({"verdict": f"{STATUS[status][0]} {status}", "module": c["module"],
                     "function": c["function"], "allocator": c["allocator"],
                     "alloc line": c["alloc"]["line"], "exit line": c["exit"]["line"],
                     "returns": c["return_value"], "confidence": c["confidence"],
                     "failing call": ", ".join(t["callee"] for t in c["triggers"]) or "—",
                     "id": c["id"]})
    return pd.DataFrame(rows)


def finding_detail(c, v, src: Path):
    status = v.get("status", "unverified")
    icon, colour = STATUS[status]
    st.markdown(f"<span style='color:{colour};font-weight:600'>{icon} {status.upper()}</span>"
                f" — {html.escape(v.get('reason', 'not verified yet'))}", unsafe_allow_html=True)
    left, right = st.columns([3, 2])
    with left:
        st.markdown(f"**{c['function']}()** in `{src.name}`: memory from `{c['allocator']}` "
                    f"(line {c['alloc']['line']}) is neither freed nor handed over when the "
                    f"function returns **{c['return_value']}** at line {c['exit']['line']}.")
        if src.exists():
            st.markdown(source_view(src, c), unsafe_allow_html=True)
            st.caption("alloc = allocation site · fails = call whose failure leads to the "
                       "leak · exit = leaking return")
    with right:
        st.markdown(f"**Category:** {c['category']}  \n**Confidence:** {c['confidence']}")
        fx = next((f for f in fixes if f["id"] == c["id"]), None)
        if fx:
            st.markdown(f"**Fix patch:** {fx['status']} — {fx.get('reason', '')}")
            if fx.get("patch"):
                st.code(fx["patch"], language="diff")
        for t in v.get("tests", []):
            st.markdown(f"**Runtime test** `fail-nth={t['fail_nth']}` → fault at "
                        f"`{t['expected_frame'] or 'silent fault'}`: {t['fault_hits']} of "
                        f"{t['attempts']} attempts hit, {len(t['leaks'])} object(s) leaked")
            for lk in t["leaks"][:2]:
                st.code(f"unreferenced object (size {lk['size']})\n  " + "\n  ".join(lk["backtrace"]),
                        language="text")


# --------------------------------------------------------------- layout -----
st.sidebar.title("🛡️ KernelLeakGuard")
st.sidebar.caption("Hybrid static analysis and runtime verification of memory leaks on "
                   "Linux kernel early-exit paths")
page = st.sidebar.radio("View", ["Overview", "Findings", "Fix patches", "Real kernel code",
                                 "Evaluation", "Run pipeline"], key="page")
rs = run_state()
if rs["running"]:
    st.sidebar.info(f"⏳ `klg {rs.get('step')}` running for "
                    f"{int(time.time() - rs.get('started', time.time()))} s")

if page == "Overview":
    st.title("KernelLeakGuard")
    n = {s: sum(1 for v in verdicts.values() if v["status"] == s)
         for s in ("confirmed", "not-reproduced", "inconclusive")}
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Modules analysed", len(static))
    c2.metric("Static warnings", len(cands))
    c3.metric("Confirmed leaks", n["confirmed"])
    c4.metric("Refuted (not reproduced)", n["not-reproduced"])
    c5.metric("Inconclusive", n["inconclusive"])
    if ev.get("approaches", {}).get("hybrid"):
        hy, stc = ev["approaches"]["hybrid"], ev["approaches"]["static/full"]
        st.markdown(f"**Static only:** precision {stc['precision']:.2f}, recall {stc['recall']:.2f}"
                    f" &nbsp;→&nbsp; **Hybrid:** precision {hy['precision']:.2f}, recall "
                    f"{hy['recall']:.2f} (ground truth: {ev['ground_truth']['leak_sites']} leaking "
                    f"and {ev['ground_truth']['safe_sites']} safe allocation sites)")
    if fixes:
        ok = sum(1 for f in fixes if f["status"] == "validated")
        st.markdown(f"**Fix patches:** {ok} of {len(fixes)} confirmed leaks have a generated "
                    "patch validated by compilation, re-analysis and a VM re-run.")
    st.subheader("Pipeline")
    st.markdown(
        "1. **Static analysis** (C++/LLVM): kernel C → LLVM IR → allocation tracking, ownership "
        "and escape analysis, path search to early exits, failing-call prediction\n"
        "2. **Fault-point sweep** (QEMU/KVM guest): `fail-nth` maps every fault point of each "
        "routine to its source line\n"
        "3. **Targeted fault injection**: fail exactly the call that leads onto the leaking path\n"
        "4. **Kmemleak verification**: unreferenced objects attributed to the allocation site → "
        "confirmed / not reproduced / inconclusive\n"
        "5. **Fix patches**: generated and validated by compiling, re-analysing and re-running "
        "the failing test")

elif page == "Findings":
    st.title("Findings on the benchmark corpus")
    if not cands:
        st.info("No static results yet. Run the pipeline first.")
    else:
        df = finding_table(cands, verdicts)
        f1, f2 = st.columns(2)
        s_status = f1.multiselect("Verdict", sorted(df["verdict"].unique()))
        s_conf = f2.multiselect("Confidence", ["high", "medium", "low"])
        mask = pd.Series(True, index=df.index)
        if s_status:
            mask &= df["verdict"].isin(s_status)
        if s_conf:
            mask &= df["confidence"].isin(s_conf)
        view = df[mask]
        st.dataframe(view.drop(columns=["id"]), width="stretch", hide_index=True)
        if len(view):
            choice = st.selectbox("Inspect finding", view["id"].tolist(),
                                  format_func=lambda i: i.replace(":", "  ·  "))
            c = next(x for x in cands if x["id"] == choice)
            finding_detail(c, verdicts.get(choice, {}), config.CORPUS / f"{c['module']}.c")

elif page == "Fix patches":
    st.title("Generated fix patches")
    if not fixes:
        st.info("No patches yet. Run step `fix` on the Run pipeline page.")
    else:
        df = pd.DataFrame([{"module": f["module"], "function": f["function"],
                            "status": f["status"], "compiles": f["checks"].get("compiles"),
                            "static clean": f["checks"].get("static_clean"),
                            "runtime clean": f["checks"].get("runtime_clean"),
                            "reason": f.get("reason", "")} for f in fixes])
        st.dataframe(df, width="stretch", hide_index=True)
        pick = st.selectbox("Show patch", [f["id"] for f in fixes],
                            format_func=lambda i: i.replace(":", "  ·  "))
        fx = next(f for f in fixes if f["id"] == pick)
        st.markdown(f"**{fx['status']}** — {fx.get('reason', '')}")
        if fx.get("patch"):
            st.code(fx["patch"], language="diff")

elif page == "Real kernel code":
    st.title("Real Linux 6.18.55 kernel modules")
    real = config.RESULTS / "real"
    summ = _json(real / "summary.json", {})
    if not summ:
        st.info("No results yet. Run step `real` on the Run pipeline page.")
    else:
        r_static, r_ver = load(str(real))
        r_verdicts = {v["id"]: v for v in r_ver.get("verdicts", [])}
        r_cands = [c for r in r_static.values() for c in r.get("candidates", [])]
        triage = {t["id"]: t for t in _json(real / "triage.json", [])}
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Modules", summ.get("modules", 0))
        c2.metric("Functions analysed", summ.get("functions", 0))
        c3.metric("Static warnings", len(r_cands))
        c4.metric("Fault points exercised", summ.get("fault_points", 0))
        c5.metric("VM crashes recovered", summ.get("crashes", 0))
        st.markdown(summ.get("headline", ""))
        if r_cands:
            df = finding_table(r_cands, r_verdicts)
            df["manual review"] = [triage.get(i, {}).get("label", "—") for i in df["id"]]
            st.dataframe(df.drop(columns=["id"]), width="stretch", hide_index=True)
            choice = st.selectbox("Inspect warning", df["id"].tolist(),
                                  format_func=lambda i: i.replace(":", "  ·  "))
            c = next(x for x in r_cands if x["id"] == choice)
            if choice in triage:
                st.markdown(f"**Manual review:** {triage[choice]['label']} — {triage[choice]['note']}")
            src = Path(c.get("source_path", ""))
            finding_detail(c, r_verdicts.get(choice, {}), src)
        dyn = summ.get("dynamic_leaks", [])
        st.subheader("Leaks found by exhaustive fault injection in module init")
        if dyn:
            st.dataframe(pd.DataFrame(dyn), width="stretch", hide_index=True)
        else:
            st.markdown("None: every injected failure in the initialisation of these modules "
                        "released its memory correctly.")
        rc = _json(real / "root_causes.json", {})
        if rc:
            st.subheader("Root causes of the findings on real code")
            for key, title in (("slub_sysfs_leak", "Slab-cache leak in the SLUB allocator"),
                               ("f2fs_sysfs_leak", "Kobject-name leak in f2fs (regression from 2026)"),
                               ("ntfs3_do_action_leak", "Leak in ntfs3 log replay (static finding)"),
                               ("ufs_bforget_leak", "Leak in ufs truncation (static finding, known since 2018)"),
                               ("null_blk_crash", "Use-after-free of module memory (null_blk)")):
                f = rc.get(key)
                if not f:
                    continue
                st.markdown(f"**{title}** — `{f['component']}`  \n**Trigger:** "
                            f"{f.get('trigger', f.get('found_by', ''))}")
                st.markdown("\n".join(f"{i}. {m}" for i, m in enumerate(f["mechanism"], 1)))
                st.markdown(f"**Upstream:** {f['upstream']}")
                if key == "slub_sysfs_leak":
                    a, b = f["stock"], f["patched"]
                    st.markdown(f"**Fix validated in the VM:** stock kernel {a['unreferenced']} "
                                f"leaked objects in {a['leaking_batches']}/{a['batches']} batches; "
                                f"patched kernel {b['unreferenced']} (sysfs failure exercised "
                                f"{b['sysfs_failures_exercised']} times).")
                    patch = config.ROOT / f["patch"]
                    if patch.exists():
                        with st.expander("Patch"):
                            st.code(patch.read_text(), language="diff")
                elif key == "f2fs_sysfs_leak":
                    ib = f["introduced_by"]
                    st.markdown(f"**Introduced by** {ib['commit']} \"{ib['subject']}\" ({ib['date']}): "
                                f"{ib['note']}.  \n**Fix validated in the VM:** stock "
                                f"{sum(f['stock_leaked_names'].values())} leaked names, patched "
                                f"{sum(f['patched_leaked_names'].values())}.")
                    patch = config.ROOT / f["patch"]
                    if patch.exists():
                        with st.expander("Patch"):
                            st.code(patch.read_text(), language="diff")
                elif key in ("ntfs3_do_action_leak", "ufs_bforget_leak"):
                    v = f["validation"]
                    st.markdown(f"**Fix validated statically:** compiles; warnings "
                                f"{v['warnings_original']} → {v['warnings_patched']}, none new. "
                                f"Runtime: {f['runtime']}.")
                    patch = config.ROOT / f["patch"]
                    if patch.exists():
                        with st.expander("Patch"):
                            st.code(patch.read_text(), language="diff")
                else:
                    st.markdown(f"**Crashed at fault points:** {f['crashed']} of {f['probed']}  \n"
                                f"**Fix:** {f['fix']}")
        seeds = _json(config.RESULTS / "seeded" / "summary.json", [])
        if seeds:
            st.subheader("Seeded leaks (detect → confirm → fix on real code)")
            st.dataframe(pd.DataFrame([{
                "module": s["module"], "function": s["function"], "removed": s["removed"],
                "origin": (f"real bug, fixed upstream by {s['history']['commit']}"
                           if s.get("history") else "seeded by us"),
                "line": s["removed_line"], "detected": s["detected"],
                "confirmed (VM)": s.get("confirmed"), "fixed": s.get("fixed")} for s in seeds]),
                width="stretch", hide_index=True)
            for s in seeds:
                for e in s.get("evidence", [])[:1]:
                    st.markdown(f"**{s['module']}:** {e['reason']}")
                    st.code("\n".join(e.get("backtrace", [])[:8]))
                if s.get("fix_patch"):
                    with st.expander(f"{s['module']} fix patch"):
                        st.code(s["fix_patch"], language="diff")

elif page == "Evaluation":
    st.title("Evaluation")
    if not ev.get("approaches"):
        st.info("No evaluation yet. Run the full pipeline.")
    else:
        recs = [{"approach": k, "TP": m["tp"], "FP": m["fp"], "FN": m["fn"],
                 "precision": m["precision"], "recall": m["recall"], "F1": m["f1"],
                 "executions": m.get("executions")} for k, m in ev["approaches"].items()]
        df = pd.DataFrame(recs)
        st.dataframe(df, width="stretch", hide_index=True)
        long = df.melt(id_vars="approach", value_vars=["precision", "recall"],
                       var_name="metric", value_name="value")
        chart = (alt.Chart(long).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
                 .encode(x=alt.X("approach:N", sort=None, title=None), xOffset="metric:N",
                         y=alt.Y("value:Q", scale=alt.Scale(domain=[0, 1]), title=None),
                         color=alt.Color("metric:N", scale=alt.Scale(range=SERIES),
                                         legend=alt.Legend(orient="top", title=None)),
                         tooltip=["approach", "metric", alt.Tooltip("value:Q", format=".2f")])
                 .properties(height=320, title="Precision and recall per approach"))
        st.altair_chart(chart, width="stretch")
        if ev.get("triage"):
            st.subheader("What runtime verification did with each static warning")
            st.dataframe(pd.DataFrame([{"verdict": s, "ground truth": g, "warnings": n}
                                       for s, d in ev["triage"].items() for g, n in d.items()]),
                         width="stretch", hide_index=True)

elif page == "Run pipeline":
    st.title("Run the pipeline")
    st.markdown("Each step runs `python3 -m klg <step>` as a background process. The log "
                "below refreshes every two seconds; you can switch pages or reload the browser "
                "while it runs.")
    step = st.selectbox("Step", list(STEPS), format_func=lambda s: f"{s} — {STEPS[s]}",
                        disabled=rs["running"])
    b1, b2, _ = st.columns([1, 1, 4])
    if b1.button("▶ Run", type="primary", disabled=rs["running"]):
        start_run(step)
        st.rerun()
    if b2.button("■ Stop", disabled=not rs["running"]):
        stop_run(rs["pid"])
        st.rerun()

    @st.fragment(run_every=2)
    def live_log():
        s = run_state()
        if s["running"]:
            st.info(f"Running `klg {s.get('step')}` — "
                    f"{int(time.time() - s.get('started', time.time()))} s elapsed")
        elif s["exit"] is not None:
            (st.success if s["exit"] == 0 else st.error)(
                f"`klg {s.get('step')}` finished with exit code {s['exit']}")
        if s["log"]:
            st.code(s["log"][-8000:], language="text")
        if not s["running"] and st.session_state.get("was_running"):
            st.session_state["was_running"] = False
            st.cache_data.clear()
            st.rerun()
        st.session_state["was_running"] = s["running"]

    live_log()
