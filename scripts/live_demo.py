"""Live demonstration inside the real guest kernel (Linux 6.18.55 under QEMU).

    python3 scripts/live_demo.py                   # narrated demo on the terminal
    python3 scripts/live_demo.py shell             # root shell in the guest ('poweroff -f' to leave)
    python3 scripts/live_demo.py --window          # same demo on the VM's own screen (QEMU window)
    python3 scripts/live_demo.py shell --window    # root shell on the VM's screen: click and type
    python3 scripts/live_demo.py --step [--window] # one step at a time: press Enter for the next

--window shows the virtual machine's own screen (like a VirtualBox/VMware window):
QEMU serves the screen over VNC and the browser shows it with the noVNC viewer
(dashboard/novnc), so keyboard and mouse work and nothing depends on WSLg. The
kernel's boot log and every demo command appear on the VM's screen; the serial
console still mirrors the demo on the terminal. VM screen:
http://localhost:6080/vnc_lite.html?host=localhost&port=5701&path=&scale=true

The demo boots our kernel and shows, with the kernel's own output:
  1. the kernel and its leak/fault-injection machinery;
  2. the real erofs module loading cleanly;
  3. one allocation failed with fail-nth while erofs initialises (fault 85):
     kmemleak reports the leaked slab cache and the kernel warns in
     kmem_cache_destroy() -> the SLUB bug (results/real/root_causes.json);
  4. the bonding leak that Linux shipped until commit 8d6184e4881b,
     re-introduced into today's code: kmemleak reports the leaked net_device.
Under software emulation (no KVM) the whole run takes a few minutes.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from klg import config, real, verify  # noqa: E402

BONDING = (config.RESULTS / "seeded" / "bonding_bond_create_8d6184e4881b" / "buggy" / "bonding.ko")

DEMO_HEAD = r'''
D=/sys/kernel/debug
PAUSE=${PAUSE:-2}
STEP=${STEP:-0}
# Step mode: wait for Enter from the VM screen's keyboard (tty0) or from the
# terminal / dashboard (serial line ttyS0), whichever comes first.
wait_enter() {
  printf '\033[2m   ... press Enter to run this step\033[0m\n'
  rm -f /tmp/go
  ( read x < /dev/tty0 2>/dev/null && touch /tmp/go ) & r1=$!
  ( read x < /dev/ttyS0 2>/dev/null && touch /tmp/go ) & r2=$!
  while [ ! -f /tmp/go ]; do sleep 0.2; done
  kill $r1 $r2 2>/dev/null
}
say()  { printf '\n\033[1;36m==== %s\033[0m\n' "$*"
         if [ "$STEP" = 1 ]; then wait_enter; else sleep $PAUSE; fi; }
run()  { printf '\033[1;33m# %s\033[0m\n' "$*"; sh -c "$*"; sleep 1; }
scan() { sleep 5; echo scan > $D/kmemleak; echo scan > $D/kmemleak; }
log()  { :; }
# kmemleak shows raw addresses for frames in a module that is already unloaded;
# klg_modwatch logged its symbols (KLG-SYM lines): name the nearest one.
symbolize() {
  dmesg | grep 'KLG-SYM' | grep -v ' \.L' > /tmp/syms
  awk 'NR==FNR { m[NR]=$(NF-2); a[NR]=$(NF-1); n[NR]=$NF; c=NR; next }
       /^ +0xffffffff[0-9a-f]+$/ { t=substr($1,3); best=""
         for (i=1; i<=c; i++) if (a[i] <= t && a[i] > best) { best=a[i]; bm=m[i]; bn=n[i] }
         if (best != "") { print $0 "   <- " bn " [" bm "]"; next } }
       { print }' /tmp/syms -
}
demo() {
insmod /mnt/host/mods/klg_modwatch.ko 2>/dev/null
scan; echo clear > $D/kmemleak; dmesg -c > /dev/null

say "1. Our own Linux kernel, running in QEMU (not the laptop's kernel)"
run "uname -r -v"
run "cat /proc/cmdline"
run "ls $D/kmemleak $D/failslab /proc/self/fail-nth"

say "2. Load and unload the real erofs module normally"
run "insmod /mnt/host/mods/erofs.ko && lsmod | grep '^erofs' && rmmod erofs"
scan
run "grep -c 'unreferenced object' $D/kmemleak || true"
echo "(0 = kmemleak finds no leak)"

say "3. Fail exactly ONE allocation (fault 85) while erofs initialises"
run "klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth 85 --count 1 --filter erofs --out /tmp/erofs.log | tail -2"
echo "--- the injected failure (kernel log):"
dmesg | grep -A16 'FAULT_INJECTION: forcing a failure' | grep -E 'FAULT_INJECTION|kmalloc|sysfs_slab_add|do_kmem_cache_create|__kmem_cache_create_args|init_module' | head -7
scan
say "4. kmemleak: the slab cache was leaked"
printf '\033[1;33m# %s\033[0m\n' "grep -A12 'unreferenced object' $D/kmemleak | head -14"
grep -A12 'unreferenced object' $D/kmemleak | head -14 | symbolize
say "5. The kernel's own warning when erofs destroyed that cache (the SLUB bug)"
dmesg | grep -A9 'is not initialized, yet kobject_put' | grep -E 'kobject|z_erofs|cleanup_module|delete_module' | head -6
dmesg | grep -m1 'refcount_t: underflow'
echo clear > $D/kmemleak; dmesg -c > /dev/null

if [ -f /mnt/host/mods/bonding.ko ]; then
dmesg -c > /dev/null
say "6. A real historical bug: bonding as shipped before commit 8d6184e4881b (2010)"
echo "bond_create() forgets free_netdev() when register_netdevice() fails."
run "klg-agent repeat --mode init --target /mnt/host/mods/bonding.ko --nth 27 --count 1 --filter bonding --out /tmp/bond.log | tail -2"
scan
say "7. kmemleak: the net_device allocated in bond_create() was leaked"
printf '\033[1;33m# %s\033[0m\n' "grep -A12 'unreferenced object' $D/kmemleak | head -14"
grep -A12 'unreferenced object' $D/kmemleak | head -14 | symbolize
fi

say "Done. Every line above was printed by the running kernel."
}
'''
# Terminal / dashboard: the serial console is the only console.
DEMO_SERIAL = DEMO_HEAD + "demo > /dev/console 2>&1\nsleep 3\n"
# VM window: kernel messages stay off the screen during the demo (the demo shows
# the relevant kernel log lines itself); output goes to the VM screen and serial.
DEMO_WINDOW = DEMO_HEAD + r'''
dmesg -n 1
demo 2>&1 | tee /dev/ttyS0 > /dev/tty0
printf '\n\033[1;36mClick this screen and press Enter to power off (or wait 2 minutes).\033[0m\n' > /dev/tty0
read -t 120 x < /dev/tty0
'''


NOVNC_PORT, VNC_WS_PORT = 6080, 5701
SCREEN_URL = (f"http://localhost:{NOVNC_PORT}/vnc_lite.html?host=localhost&port={VNC_WS_PORT}"
              "&path=&scale=true")


def serve_viewer():
    """Serve the noVNC viewer (static files) on localhost:6080 unless already running."""
    import socket
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", NOVNC_PORT)) == 0:
            return
    subprocess.Popen([sys.executable, "-m", "http.server", str(NOVNC_PORT), "--bind", "127.0.0.1",
                      "--directory", str(config.ROOT / "dashboard" / "novnc")],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def open_screen_later():
    """Open the VM screen in the Windows browser once QEMU's VNC server listens."""
    cmd = (f"for i in $(seq 1 40); do (exec 3<>/dev/tcp/127.0.0.1/{VNC_WS_PORT}) 2>/dev/null && break; "
           f"sleep 0.5; done; powershell.exe -NoProfile -Command \"Start-Process '{SCREEN_URL}'\"")
    subprocess.Popen(["bash", "-c", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


def stop_previous(share: Path):
    """Stop a live-demo VM that is still running (e.g. a demo started twice); it
    holds the VM-screen ports and its shared folder is about to be replaced.
    Only QEMU processes using this demo's share folder are touched."""
    import signal
    import time
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            cmd = (proc / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if cmd and cmd[0].endswith(b"qemu-system-x86_64") and \
                any(f"path={share},".encode() in a for a in cmd):
            print(f"Stopping the previous live-demo VM (pid {proc.name}) ...", flush=True)
            os.kill(int(proc.name), signal.SIGTERM)
            for _ in range(20):
                if not (proc / "cmdline").exists():
                    break
                time.sleep(0.25)


def main():
    args = sys.argv[1:]
    window = "--window" in args
    mode = "shell" if "shell" in args else "demo"
    share = (config.ROOT / ".scratch" / "live_demo").resolve()
    stop_previous(share)
    mods = real.built_modules()
    verify.PRELOAD.clear()
    step = ["STEP=1"] if "--step" in args else []      # wait for Enter before each step
    job = [] if mode == "shell" else (step + (["PAUSE=5", DEMO_WINDOW] if window else [DEMO_SERIAL]))
    verify._write_share(share, {"erofs": {"ko": mods["erofs"]}}, job)
    if BONDING.exists():
        shutil.copy(BONDING, share / "mods" / "bonding.ko")
    if mode == "shell":
        (share / "job.sh").unlink()          # no job: the guest init drops to a root shell
        print("Root shell in the guest kernel"
              + (" on the VM screen in the browser: click into it and type." if window else ".")
              + " Modules are in /mnt/host/mods. Leave with: poweroff -f")
    env_sh = config.ROOT / "vm" / "env.sh"
    out = subprocess.run(["bash", "-c", f"source {env_sh}; echo $BZIMAGE; echo $INITRAMFS"],
                         capture_output=True, text=True, check=True).stdout.split()
    bzimage, initramfs = out[0], out[1]
    kvm = os.access("/dev/kvm", os.W_OK) and "svm" in Path("/proc/cpuinfo").read_text()
    accel = ["-enable-kvm", "-cpu", "host"] if kvm else ["-accel", "tcg,thread=multi", "-cpu", "max"]
    common = "kmemleak=on panic=-1 nokaslr init_on_alloc=1 init_on_free=1"
    # Window: the screen (tty0) is the main console and shows the boot log.
    cmdline = (f"console=ttyS0 console=tty0 loglevel=7 {common}" if window
               else f"console=ttyS0 quiet loglevel=4 {common}")
    print(f"Booting Linux 6.18.55 ({'KVM' if kvm else 'software emulation, ~30 s to boot'}) ...",
          flush=True)
    if window:
        serve_viewer()
        if not os.environ.get("LIVE_NO_BROWSER"):
            open_screen_later()
        print(f"VM screen: {SCREEN_URL}", flush=True)
    os.execvp("qemu-system-x86_64", [
        "qemu-system-x86_64", *accel, "-smp", "2", "-m", "2G",
        "-kernel", bzimage, "-initrd", initramfs, "-append", cmdline,
        "-virtfs", f"local,path={share},mount_tag=host0,security_model=none,id=host0",
        "-no-reboot", "-name", "KernelLeakGuard VM - Linux 6.18.55",
        "-audio", "none",                       # no sound card (avoids PipeWire messages)
        *(["-display", "none", "-vga", "std",
           "-vnc", f"127.0.0.1:{VNC_WS_PORT - 5700},websocket=on",
           "-serial", "stdio",
           # LIVE_MONITOR=path: QEMU monitor socket (tests take VM screenshots with it)
           "-monitor", (f"unix:{os.environ['LIVE_MONITOR']},server,nowait"
                        if os.environ.get("LIVE_MONITOR") else "none")] if window
          else ["-nographic", "-serial", "mon:stdio"])])


if __name__ == "__main__":
    main()
