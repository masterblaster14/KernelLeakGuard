#!/usr/bin/env bash
# Build a guest kernel (bzImage only) with one kernel patch applied, in its own
# O= directory, leaving the shared kernel source and the main build untouched
# (patched files are restored with their original timestamps).
#
#   bash scripts/build_patched_kernel.sh patches/0001-....patch ~/klg-build/kbuild-slubfix
#   PROBE_KBUILD=~/klg-build/kbuild-slubfix python3 scripts/fault_probe.py erofs 85 85 1 OUT
set -euo pipefail
PATCH=$(realpath "$1"); OUT=$2
source "$(dirname "${BASH_SOURCE[0]}")/../vm/env.sh"
SAVE=$(mktemp -d)
FILES=$(grep -E '^\+\+\+ b/' "$PATCH" | sed 's|^+++ b/||; s|\t.*||')
for f in $FILES; do mkdir -p "$SAVE/$(dirname "$f")"; cp -p "$KSRC/$f" "$SAVE/$f"; done
restore() { for f in $FILES; do cp -p "$SAVE/$f" "$KSRC/$f"; done; rm -rf "$SAVE"; }
trap restore EXIT
patch -d "$KSRC" -p1 --no-backup-if-mismatch < "$PATCH"
mkdir -p "$OUT"; cp "$KBUILD/.config" "$OUT/.config"
make -C "$KSRC" O="$OUT" LLVM=1 olddefconfig > /dev/null
make -C "$KSRC" O="$OUT" LLVM=1 -j"$(nproc)" bzImage > "$OUT/build.log" 2>&1
ls -la "$OUT/arch/x86/boot/bzImage"
