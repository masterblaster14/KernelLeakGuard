#!/usr/bin/env bash
# Get everything ready for the demo with one command:
#
#   bash scripts/demo_ready.sh          # check everything, start the dashboard
#   bash scripts/demo_ready.sh --open   # ... and open the dashboard, report and slides on Windows
#
# Every check prints ✔ or ✘ with what to do. The demo itself is in DEMO.md.
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/.."
ROOT=$PWD
FAIL=0
ok()   { printf '  \033[32m✔\033[0m %s\n' "$*"; }
bad()  { printf '  \033[31m✘\033[0m %s\n' "$*"; FAIL=1; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }

echo "KernelLeakGuard demo check"
source vm/env.sh
[[ -f $BZIMAGE ]]   && ok "guest kernel: our Linux $KVER build"     || bad "guest kernel missing: run ./vm/build_kernel.sh"
[[ -f $INITRAMFS ]] && ok "guest file system (initramfs)"           || bad "initramfs missing: run ./vm/build_initramfs.sh"
command -v qemu-system-x86_64 >/dev/null && ok "QEMU (virtual machine)" || bad "QEMU missing: sudo apt install qemu-system-x86"
[[ -x analyzer/build/klg-analyze ]] && ok "static analyser (klg-analyze)" || bad "analyser not built: make -C analyzer"
python3 - <<'EOF' && ok "real erofs module (Linux build)" || bad "erofs.ko missing: run ./vm/build_kernel.sh"
import sys; sys.path.insert(0, ".")
from klg import real
sys.exit(0 if real.built_modules().get("erofs", None) and real.built_modules()["erofs"].exists() else 1)
EOF
[[ -f results/seeded/bonding_bond_create_8d6184e4881b/buggy/bonding.ko ]] \
    && ok "bonding module with the 2010 bug" || bad "bonding seed missing: python3 -m klg seed --only bonding_bond_create_8d6184e4881b"
for f in results/evaluation.json results/real/summary.json results/real/root_causes.json results/seeded/summary.json; do
    [[ -f $f ]] || bad "result missing: $f"
done
[[ $FAIL == 0 ]] && ok "recorded results (benchmark, real kernel, root causes, seeds)"
[[ -x .venv/bin/streamlit ]] && ok "Python environment" || bad "venv missing: ./scripts/setup_venv.sh"
[[ -f dashboard/novnc/vnc_lite.html ]] && ok "VM screen viewer (noVNC, opens in the browser)" \
    || bad "dashboard/novnc missing (VM screen viewer)"
if [[ -w /dev/kvm ]] && grep -qw svm /proc/cpuinfo; then ok "KVM: the VM runs at full speed"
else warn "no KVM: the VM uses software emulation (boot ~30 s, demo ~1-2 min); that is fine"; fi
if pgrep -f "qemu-system-x86_64" >/dev/null; then warn "a VM is still running (let it finish, or: pkill qemu-system)"; fi

# Dashboard
if curl -sf -o /dev/null http://localhost:8501; then
    ok "dashboard already running: http://localhost:8501"
else
    setsid nohup .venv/bin/streamlit run dashboard/app.py --server.headless true \
        --server.port 8501 > .scratch/dashboard.log 2>&1 < /dev/null &
    for _ in $(seq 1 40); do curl -sf -o /dev/null http://localhost:8501 && break; sleep 1; done
    curl -sf -o /dev/null http://localhost:8501 && ok "dashboard started: http://localhost:8501" \
        || bad "dashboard did not start: see .scratch/dashboard.log"
fi

if [[ ${1:-} == --open ]]; then
    explorer.exe "http://localhost:8501" 2>/dev/null
    explorer.exe "$(wslpath -w "$ROOT/docs/KernelLeakGuard_Presentation.pdf")" 2>/dev/null
    explorer.exe "$(wslpath -w "$ROOT/docs/KernelLeakGuard_Final_Report.pdf")" 2>/dev/null
    ok "opened the dashboard, slides and report on Windows"
fi

echo
if [[ $FAIL == 0 ]]; then
    printf '\033[1;32mReady.\033[0m  Commands for the demo (see DEMO.md):\n'
else
    printf '\033[1;31mFix the ✘ items first.\033[0m  Commands for the demo (see DEMO.md):\n'
fi
cat <<'EOF'
  python3 -m klg show                           # what the tool found (benchmark)
  python3 scripts/live_demo.py --window         # LIVE: real kernel catches the leaks (VM screen opens in the browser)
  python3 scripts/live_demo.py shell --window   # root shell on the VM screen (poweroff -f to leave)
EOF
exit $FAIL
