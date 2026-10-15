#!/usr/bin/env bash
# Regenerate every deliverable from the latest results:
# test results, figures, final report, proposal, Review-I report, user manual, slides.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY=.venv/bin/python

STREAMLIT_LOGGER_LEVEL=error PYTHONWARNINGS=ignore \
    $PY -m unittest discover -s tests -v > results/test_results.txt 2>&1 || true
tail -3 results/test_results.txt
LAST=$(ls -t results/runs/run_*.log 2>/dev/null | head -1 || true)
if [[ -n "$LAST" ]]; then
    { echo "$ python3 -m klg all"; grep -E "^\[klg\]|^\||^Triage|^  (confirmed|inconclusive|not-reproduced)" "$LAST"; } \
        > results/pipeline_demo.log
fi
{ echo "$ python3 -m klg show"; python3 -m klg show; } > results/show_demo.log
$PY -m klg.figures
$PY docs/build_report.py
$PY docs/build_reviews.py
$PY docs/build_manual.py
$PY docs/build_ppt.py
