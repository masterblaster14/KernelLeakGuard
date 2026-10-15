#!/usr/bin/env bash
# Build the guest initramfs: static busybox + KernelLeakGuard init + klg-agent.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/vm/env.sh"

BUSYBOX="$(command -v busybox || true)"
[[ -n "$BUSYBOX" ]] || { echo "busybox-static is not installed"; exit 1; }
file -L "$BUSYBOX" 2>/dev/null | grep -q "statically linked" || \
    { echo "$BUSYBOX is not statically linked (install busybox-static)"; exit 1; }

make -C "$ROOT/runtime" >/dev/null

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE"/{bin,sbin,proc,sys,dev,tmp,mnt/host}
cp "$BUSYBOX" "$STAGE/bin/busybox"
cp "$ROOT/vm/init" "$STAGE/init"
cp "$ROOT/runtime/klg-agent" "$STAGE/bin/klg-agent"
chmod +x "$STAGE/init" "$STAGE/bin/busybox" "$STAGE/bin/klg-agent"

mkdir -p "$(dirname "$INITRAMFS")"
(cd "$STAGE" && find . -print0 | cpio --null -o -H newc --quiet | gzip -9) > "$INITRAMFS"
ls -lh "$INITRAMFS"
