"""Render a Markdown guide as a printable PDF.

    .venv/bin/python scripts/build_demo_guide.py                       # DEMO.md
    .venv/bin/python scripts/build_demo_guide.py GUIDE.md docs/KernelLeakGuard_Study_Guide.pdf

Markdown -> HTML (images embedded) -> PDF with Microsoft Edge in headless mode
(Windows, reached from WSL). Needs the `markdown` package in the venv.
"""
import base64
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
EDGE = Path("/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
SRC = ROOT / (sys.argv[1] if len(sys.argv) > 1 else "DEMO.md")
OUT = ROOT / (sys.argv[2] if len(sys.argv) > 2 else "docs/KernelLeakGuard_Demo_Guide.pdf")

CSS = """
@page { size: A4; margin: 16mm 15mm; }
body { font: 10.5pt/1.45 "Segoe UI", Arial, sans-serif; color: #1f2328; }
h1 { font-size: 21pt; color: #12355b; border-bottom: 3px solid #2a78d6; padding-bottom: 4px; }
h2 { font-size: 15pt; color: #12355b; margin-top: 20px; page-break-after: avoid; }
h3 { font-size: 12.5pt; color: #2a78d6; margin-top: 16px; page-break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 6px 0 10px; page-break-inside: avoid; }
th, td { border: 1px solid #c9d1d9; padding: 4px 7px; vertical-align: top; text-align: left; }
th { background: #eaf2fb; }
code { font: 9.5pt Consolas, monospace; background: #f3f4f6; padding: 0 3px; border-radius: 3px; }
pre { background: #111418; color: #e6edf3; padding: 9px 11px; border-radius: 6px;
      page-break-inside: avoid; }
pre code { background: none; color: inherit; font-size: 10pt; }
img { max-width: 100%; border: 1px solid #c9d1d9; border-radius: 4px; }
img[src^="data:image/svg"] { border: 0; width: 100%; }
h1 { page-break-before: always; }
h1:first-of-type { page-break-before: avoid; }
hr { border: 0; border-top: 1px solid #d0d7de; margin: 14px 0; }
"""


def main():
    md = SRC.read_text()

    def embed(m):
        img = ROOT / m.group(2)
        data = base64.b64encode(img.read_bytes()).decode()
        mime = "image/svg+xml" if img.suffix == ".svg" else "image/png"
        return f"![{m.group(1)}](data:{mime};base64,{data})"
    md = re.sub(r"!\[([^\]]*)\]\(([^)]+\.(?:png|svg))\)", embed, md)
    body = markdown.markdown(md, extensions=["tables", "fenced_code"])
    html = f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body}</body></html>"
    # Edge is a Windows program: give it Windows paths in the Windows temp folder.
    win_tmp = Path(subprocess.run(["cmd.exe", "/c", "echo %TEMP%"], capture_output=True,
                                  text=True).stdout.strip())
    tmp = Path(subprocess.run(["wslpath", "-u", str(win_tmp)], capture_output=True,
                              text=True).stdout.strip())
    src, pdf = tmp / "klg_demo_guide.html", tmp / "klg_demo_guide.pdf"
    src.write_text(html)
    subprocess.run([str(EDGE), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={win_tmp}\\klg_demo_guide.pdf",
                    f"file:///{str(win_tmp).replace(chr(92), '/')}/klg_demo_guide.html"],
                   check=True, capture_output=True, timeout=120)
    shutil.copy(pdf, OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
