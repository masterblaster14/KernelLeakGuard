#!/usr/bin/env bash
# Boot the guest kernel under QEMU/KVM with a host directory shared over 9p.
#
#   vm/run_vm.sh SHARE_DIR [TIMEOUT_SECONDS]
#
# SHARE_DIR must contain job.sh (executed by the guest init) and an out/
# directory for results. The serial console is written to SHARE_DIR/console.log.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/vm/env.sh"

SHARE="$(realpath "${1:?usage: run_vm.sh SHARE_DIR [TIMEOUT]}")"
TIMEOUT="${2:-1800}"
mkdir -p "$SHARE/out"

# init_on_alloc/init_on_free: zero slab objects so that stale pointers in
# reused memory (e.g. old SLUB freelist links) cannot make kmemleak believe a
# leaked object is still referenced.
CMDLINE="console=ttyS0 quiet loglevel=4 kmemleak=on log_buf_len=16M panic=-1 oops=panic nokaslr init_on_alloc=1 init_on_free=1 ${KLG_EXTRA_CMDLINE:-}"

ACCEL="-enable-kvm -cpu host"
# /dev/kvm can exist while hardware virtualization is not exposed to this
# (WSL) VM, e.g. with Windows Memory Integrity on: then fall back to TCG.
if [[ ! -w /dev/kvm ]] || ! grep -qwE 'svm|vmx' /proc/cpuinfo; then
    echo "[klg] KVM not usable, falling back to TCG software emulation (much slower)"
    ACCEL="-accel tcg,thread=multi -cpu max"
fi

timeout --foreground "$TIMEOUT" qemu-system-x86_64 \
    $ACCEL -smp 2 -m 2G \
    -kernel "$BZIMAGE" -initrd "$INITRAMFS" \
    -append "$CMDLINE" \
    -virtfs "local,path=$SHARE,mount_tag=host0,security_model=none,id=host0" \
    -nographic -no-reboot -serial mon:stdio \
    > "$SHARE/console.log" 2>&1 && rc=0 || rc=$?
grep -E "KLG-(GUEST-READY|JOB-EXIT)" "$SHARE/console.log" || true
exit $rc
