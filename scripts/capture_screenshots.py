"""Capture the screenshots used in the documents (docs/figures/ss_*.png).

    .venv/bin/python scripts/capture_screenshots.py [dashboard] [vm] [terminal]

dashboard: every dashboard page, rendered by Microsoft Edge (headless, Windows)
vm:        the virtual machine's own screen at each step of the live demo and in
           a shell session (QEMU screendump), plus the VM screen in the browser
terminal:  real command output rendered as terminal images

Needs the dashboard running (bash scripts/demo_ready.sh) for 'dashboard'.
"""
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from klg import figures  # noqa: E402
from PIL import Image  # noqa: E402

FIG = ROOT / "docs" / "figures"
SCRATCH = ROOT / ".scratch" / "capture"
EDGE = "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
DASH = "http://localhost:8501"
VNC_URL = "http://localhost:6080/vnc_lite.html?host=localhost&port=5701&path=&scale=true"
ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1bc")


def win_temp() -> tuple[str, Path]:
    w = subprocess.run(["cmd.exe", "/c", "echo %TEMP%"], stdout=subprocess.PIPE, text=True,
                       stderr=subprocess.DEVNULL, cwd="/mnt/c").stdout.strip()
    return w, Path(subprocess.run(["wslpath", "-u", w], capture_output=True, text=True).stdout.strip())


def edge_shot(url: str, out: Path, w: int, h: int, wait_ms: int = 12000):
    """Screenshot a page with headless Edge (a real Windows browser)."""
    wdir, ldir = win_temp()
    tmp = ldir / "klg_capture.png"
    tmp.unlink(missing_ok=True)
    subprocess.run([EDGE, "--headless=new", "--hide-scrollbars", f"--window-size={w},{h}",
                    f"--timeout={wait_ms}", f"--screenshot={wdir}\\klg_capture.png", url],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    Image.open(tmp).save(out)
    print("  ", out.name)


# ---------------------------------------------------------------- dashboard --
def page_shot(url: str, out: Path, wait: int = 20, scale: float = 1.0):
    """Normal Edge window off-screen + PrintWindow (scripts/winshot.ps1); the
    Streamlit frontend does not render in headless Edge."""
    wdir, ldir = win_temp()
    tmp = ldir / "klg_page.png"
    ps1 = subprocess.run(["wslpath", "-w", str(ROOT / "scripts" / "winshot.ps1")],
                         capture_output=True, text=True).stdout.strip()
    for attempt in range(3):
        tmp.unlink(missing_ok=True)
        r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                            ps1, "-Url", url, "-Out", wdir + "\\klg_page.png", "-W", "1500",
                            "-H", "1500", "-Wait", str(wait), "-Scale", str(scale)],
                           capture_output=True, text=True, timeout=180)
        time.sleep(4)                  # let the previous Edge instance exit completely
        if tmp.exists() and Image.open(tmp).height > 200:
            im = Image.open(tmp)
            im.crop((0, 31, im.width, im.height)).save(out)   # drop the window title bar
            print("  ", out.name, im.size)
            return
        print("   retry", out.name, r.stdout.strip()[-200:])
    raise RuntimeError(f"could not capture {url}")


def dashboard():
    live = ROOT / ".scratch" / "live_kernel"
    live.mkdir(parents=True, exist_ok=True)
    demo_log = ROOT / ".scratch" / "rehearsal_demo.log"
    if demo_log.exists():             # a finished live-demo run for the Live kernel page
        (live / "console.log").write_text(demo_log.read_text(errors="replace"))
        (live / "state.json").write_text(json.dumps({"pid": 4194300, "mode": "demo",
                                                     "window": False, "started": time.time()}))
    # A separate light-theme dashboard for printing (the user's dashboard is untouched).
    srv = subprocess.Popen([str(ROOT / ".venv" / "bin" / "streamlit"), "run", "dashboard/app.py",
                            "--server.headless", "true", "--server.port", "8502",
                            "--theme.base", "light"], cwd=ROOT, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, start_new_session=True)
    time.sleep(8)
    base = "http://localhost:8502/?page="
    shots = [("Overview", "ss_dash_overview.png"),
             ("Findings", "ss_dash_findings.png"),
             ("Findings&section=detail&finding=klg_l02_goto_ladder:sensor_setup:32:54",
              "ss_dash_finding_detail.png"),
             ("Fix%20patches", "ss_dash_fix_patches.png"),
             ("Real%20kernel%20code", "ss_dash_real.png"),
             ("Real%20kernel%20code&section=sweep", "ss_dash_real_sweep.png"),
             ("Real%20kernel%20code&section=root&rc=slub_sysfs_leak", "ss_dash_rc_slub.png"),
             ("Real%20kernel%20code&section=root&rc=f2fs_sysfs_leak", "ss_dash_rc_f2fs.png"),
             ("Real%20kernel%20code&section=root&rc=ntfs3_do_action_leak,ufs_bforget_leak",
              "ss_dash_rc_static.png"),
             ("Real%20kernel%20code&section=root&rc=null_blk_crash", "ss_dash_rc_nullblk.png"),
             ("Real%20kernel%20code&section=seeds", "ss_dash_seeds.png"),
             ("Live%20kernel", "ss_dash_live.png"),
             ("Evaluation", "ss_dash_evaluation.png"),
             ("Run%20pipeline", "ss_dash_run.png")]
    try:
        for q, name in shots:
            page_shot(base + q, FIG / name)
    finally:
        os.killpg(srv.pid, 15)


# ----------------------------------------------------------------------- vm --
KEYS = {" ": "spc", "-": "minus", "/": "slash", ".": "dot", "|": "shift-backslash",
        "_": "shift-minus", "=": "equal", ":": "shift-semicolon", "\n": "ret", "'": "apostrophe",
        "*": "shift-8", ">": "shift-dot", "^": "shift-6"}


class Monitor:
    def __init__(self, path: Path):
        self.path = path

    def cmd(self, line: str):
        with socket.socket(socket.AF_UNIX) as s:
            s.connect(str(self.path))
            time.sleep(0.2)
            s.recv(65536)
            s.sendall(line.encode() + b"\n")
            time.sleep(0.4)

    def dump(self, out: Path):
        ppm = SCRATCH / (out.stem + ".ppm")
        self.cmd(f"screendump {ppm}")
        time.sleep(0.8)
        im = Image.open(ppm)
        im.resize((im.width * 2, im.height * 2), Image.NEAREST).save(out)
        print("  ", out.name)

    def type(self, text: str):
        for ch in text:
            key = KEYS.get(ch, ("shift-" + ch.lower()) if ch.isupper() else ch)
            self.cmd(f"sendkey {key}")


def boot(mode_args, log: Path, sock: Path):
    sock.unlink(missing_ok=True)
    env = dict(os.environ, LIVE_MONITOR=str(sock), LIVE_NO_BROWSER="1")
    proc = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "live_demo.py"), *mode_args],
                            stdout=open(log, "w"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            env=env, cwd=ROOT, start_new_session=True)
    for _ in range(60):
        if sock.exists():
            break
        time.sleep(0.5)
    return proc, Monitor(sock)


def wait_for(log: Path, marker: str, timeout=240):
    t0 = time.time()
    while marker not in ANSI.sub("", log.read_text(errors="replace")):
        if time.time() - t0 > timeout:
            raise TimeoutError(marker)
        time.sleep(0.5)


def vm():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    log, sock = SCRATCH / "demo.log", SCRATCH / "mon.sock"
    proc, mon = boot(["--window"], log, sock)
    steps = [("Run /init as init process", 0.5, "ss_vm_boot.png"),
             ("==== 1.", 9, "ss_vm_step1_kernel.png"),
             ("==== 2.", 12, "ss_vm_step2_clean_load.png"),
             ("==== 3.", 14, "ss_vm_step3_fault.png"),
             ("==== 4.", 9, "ss_vm_step4_kmemleak.png"),
             ("==== 5.", 7, "ss_vm_step5_warning.png"),
             ("==== 7.", 9, "ss_vm_step7_bonding.png"),
             ("==== Done.", 3, "ss_vm_end.png")]
    for marker, delay, name in steps:
        wait_for(log, marker)
        time.sleep(delay)
        mon.dump(FIG / name)
    mon.type("\n")                     # "press Enter to power off"
    proc.wait(timeout=60)

    log, sock = SCRATCH / "shell.log", SCRATCH / "mon2.sock"
    proc, mon = boot(["shell", "--window"], log, sock)
    wait_for(log, "Run /init as init process")
    time.sleep(8)
    for c in ["uname -a\n", "lsmod\n", "ls /sys/kernel/debug/kmemleak /proc/self/fail-nth\n",
              "head -4 /proc/meminfo\n"]:
        mon.type(c)
        time.sleep(2)
    time.sleep(2)
    mon.dump(FIG / "ss_vm_shell.png")
    edge_shot(VNC_URL, FIG / "ss_vm_browser.png", 1200, 760, 10000)
    mon.type("poweroff -f\n")
    proc.wait(timeout=60)


# ----------------------------------------------------------------- terminal --
def run(cmd: str) -> list[str]:
    out = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, cwd=ROOT).stdout
    return [ANSI.sub("", l).rstrip() for l in out.splitlines()]


def terminal():
    figures.terminal("ss_term_demo_ready.png", "Ubuntu (WSL2) — bash scripts/demo_ready.sh",
                     ["$ bash scripts/demo_ready.sh"] + run("bash scripts/demo_ready.sh"), 12)
    figures.terminal("ss_term_klg_show.png", "Ubuntu (WSL2) — python3 -m klg show",
                     ["$ python3 -m klg show"] + run("python3 -m klg show")[:24], 13)
    figures.terminal("ss_term_git_log.png", "Ubuntu (WSL2) — version history",
                     ["$ git log --oneline --date=short --format='%h %ad %an  %s'"]
                     + run("git log --date=short --format='%h %ad %an  %s'")[:16], 13)
    tests = [l for l in run("STREAMLIT_LOGGER_LEVEL=error .venv/bin/python -m unittest "
                            "tests.test_klg tests.test_dashboard -v 2>&1")
             if l.strip() and not any(x in l for x in ("ScriptRunContext", "treamlit",
                                                        "ResourceWarning", "_warn("))]
    figures.terminal("ss_term_tests.png", "Ubuntu (WSL2) — unit tests",
                     ["$ .venv/bin/python -m unittest tests.test_klg tests.test_dashboard -v"]
                     + [l for l in tests if l.strip()][-30:], 13)
    figures.terminal("ss_term_analyzer.png", "Ubuntu (WSL2) — static analyser on one module",
                     ["$ analyzer/build/klg-analyze results/ir/klg_l02_goto_ladder.bc -o out.json",
                      "$ python3 -m json.tool out.json   (excerpt)"]
                     + run("analyzer/build/klg-analyze results/ir/klg_l02_goto_ladder.bc -o "
                           "/tmp/klg_l02.json --module-name klg_l02_goto_ladder >/dev/null; "
                           "python3 -c \"import json;c=json.load(open('/tmp/klg_l02.json'))"
                           "['candidates'][0];[c.pop(k,None) for k in ('path_lines','release_sites','id',"
                           "'source_path')];print(json.dumps(c,indent=2))\"")[:30], 11)
    seed = (ROOT / "results" / "seed_vm.log").read_text().splitlines()
    figures.terminal("ss_term_seed.png", "Ubuntu (WSL2) — python3 -m klg seed",
                     ["$ python3 -m klg seed"] + seed, 12)
    real = [l for l in (ROOT / "results" / "real_full.log").read_text().splitlines() if l.strip()]
    figures.terminal("ss_term_real.png", "Ubuntu (WSL2) — python3 -m klg real",
                     ["$ python3 -m klg real --skip-build"] + [l[:150] for l in real[-3:]], 13)
    patch = (ROOT / "patches" / "0001-mm-slub-release-cache-whose-sysfs-kobject-was-never-"
             "initialised.patch").read_text().splitlines()
    figures.terminal("ss_term_patch_slub.png", "patches/0001 — our fix for the SLUB leak",
                     ["$ cat patches/0001-mm-slub-release-cache-whose-sysfs-kobject-was-never-"
                      "initialised.patch"] + patch, 12)
    probe = (ROOT / "results" / "real" / "erofs_bisect.log").read_text().splitlines()
    fixed = [f"{l}" for l in (ROOT / "results" / "real" / "root_causes.json").read_text()
             .splitlines()[:0]]
    figures.terminal("ss_term_probe.png", "Ubuntu (WSL2) — finding the SLUB leak's trigger",
                     ["$ python3 scripts/fault_probe.py erofs 77 508 48 OUT     # stock kernel"]
                     + probe + fixed, 12)


def main():
    parts = sys.argv[1:] or ["dashboard", "vm", "terminal"]
    FIG.mkdir(parents=True, exist_ok=True)
    for part in parts:
        print(part)
        {"dashboard": dashboard, "vm": vm, "terminal": terminal}[part]()


if __name__ == "__main__":
    main()
