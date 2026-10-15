#!/usr/bin/env bash
# Run the complete pipeline N times (fresh VM boots each time) and keep every
# run's evaluation, to show that runtime verdicts are reproducible.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
N="${1:-3}"
mkdir -p results/runs
for i in $(seq 1 "$N"); do
    echo "=== run $i/$N"
    python3 -m klg all > "results/runs/run_$i.log" 2>&1
    cp results/evaluation.json "results/runs/evaluation_$i.json"
    cp results/runtime/verification.json "results/runs/verification_$i.json"
    grep -E "runtime verification|^\| hybrid|^\| dynamic" "results/runs/run_$i.log"
done
