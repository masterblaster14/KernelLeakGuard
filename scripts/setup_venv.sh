#!/usr/bin/env bash
# Create the Python environment for the dashboard, charts and report generation.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python -c "import streamlit, docx, pptx, matplotlib, pandas; print('venv ok, streamlit', streamlit.__version__)"
