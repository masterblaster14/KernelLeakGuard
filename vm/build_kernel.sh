#!/usr/bin/env bash
# Build the KernelLeakGuard guest kernel (Linux 6.18.55 LTS) with Clang/LLVM.
#
# The kernel is configured with kmemleak, fault injection (failslab,
# fail_function, fail_usercopy) and virtio-9p so the runtime verifier can
# inject failures and observe leaks inside a QEMU/KVM virtual machine.
set -euo pipefail
trap 'echo "[klg] KERNEL BUILD FAILED (line $LINENO); see the make output above" >&2' ERR

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/vm/env.sh"

if [[ ! -d "$KSRC" ]]; then
    echo "[klg] downloading Linux $KVER source"
    mkdir -p "$(dirname "$KSRC")"
    cd "$(dirname "$KSRC")"
    curl -sSLO "https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-$KVER.tar.xz"
    curl -sSLO "https://cdn.kernel.org/pub/linux/kernel/v6.x/sha256sums.asc"
    grep " linux-$KVER.tar.xz" sha256sums.asc | sha256sum -c -
    tar xf "linux-$KVER.tar.xz"
fi

mkdir -p "$KBUILD"
cd "$KSRC"

echo "[klg] configuring kernel in $KBUILD"
make O="$KBUILD" LLVM=1 defconfig >/dev/null
make O="$KBUILD" LLVM=1 kvm_guest.config >/dev/null
scripts/kconfig/merge_config.sh -m -O "$KBUILD" "$KBUILD/.config" \
    "$ROOT/vm/kernel.config.fragment" "$ROOT/vm/real_modules.fragment" >/dev/null
make O="$KBUILD" LLVM=1 olddefconfig >/dev/null

# Fail loudly if any option we rely on did not survive Kconfig resolution.
missing=0
while IFS= read -r line; do
    [[ "$line" =~ ^CONFIG_[A-Z0-9_]+=[ym]$ ]] || continue
    if ! grep -qx "$line" "$KBUILD/.config"; then
        echo "[klg] WARNING: $line not set in final config"
        missing=1
    fi
done < <(cat "$ROOT/vm/kernel.config.fragment" "$ROOT/vm/real_modules.fragment")
[[ $missing -eq 0 ]] && echo "[klg] all required options enabled"

echo "[klg] building bzImage with $(nproc) jobs (takes a while the first time)"
LOG="$KBUILD/klg-build.log"
make O="$KBUILD" LLVM=1 -j"$(nproc)" bzImage > "$LOG" 2>&1 || { tail -n 30 "$LOG"; false; }
tail -n 2 "$LOG"
# "modules" runs modpost over vmlinux and writes Module.symvers, which
# out-of-tree modules need to resolve kernel symbols at build time.
make O="$KBUILD" LLVM=1 -j"$(nproc)" modules >> "$LOG" 2>&1 || { tail -n 30 "$LOG"; false; }
test -f "$KBUILD/Module.symvers"

ls -lh "$KBUILD/arch/x86/boot/bzImage"
echo "[klg] kernel ready"
