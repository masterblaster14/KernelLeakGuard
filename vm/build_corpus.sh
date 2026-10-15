#!/usr/bin/env bash
# Build the benchmark corpus modules against the guest kernel.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/vm/env.sh"
make -C "$KSRC" O="$KBUILD" LLVM=1 M="$ROOT/corpus" -j"$(nproc)" modules
ls "$ROOT"/corpus/*.ko | wc -l
