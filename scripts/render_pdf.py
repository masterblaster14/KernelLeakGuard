"""Render PDF pages to PNG (for previewing generated documents).

    .venv/bin/python scripts/render_pdf.py file.pdf out_dir [first last] [--grid N]

With --grid N, pages are tiled N per image to review a long document quickly.
"""
import sys
from pathlib import Path

import fitz  # PyMuPDF

pdf, out = Path(sys.argv[1]), Path(sys.argv[2])
args = [a for a in sys.argv[3:] if not a.startswith("--")]
grid = int(sys.argv[sys.argv.index("--grid") + 1]) if "--grid" in sys.argv else 0
if grid:
    args = args[:2] if len(args) >= 2 else []
out.mkdir(parents=True, exist_ok=True)
doc = fitz.open(pdf)
first = int(args[0]) if args else 1
last = int(args[1]) if len(args) > 1 else doc.page_count
pages = list(range(first - 1, min(last, doc.page_count)))
if not grid:
    for i in pages:
        doc[i].get_pixmap(dpi=80).save(out / f"page_{i + 1:02d}.png")
else:
    cols = 3 if grid >= 6 else 2
    for start in range(0, len(pages), grid):
        chunk = pages[start:start + grid]
        pix = [doc[i].get_pixmap(dpi=55) for i in chunk]
        w, h = pix[0].width, pix[0].height
        rows = (len(chunk) + cols - 1) // cols
        sheet = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, w * cols, h * rows), False)
        sheet.clear_with(255)
        for k, p in enumerate(pix):
            p2 = fitz.Pixmap(fitz.csRGB, p) if p.n != 3 else p
            p2.set_origin((k % cols) * w, (k // cols) * h)
            sheet.copy(p2, p2.irect)
        sheet.save(out / f"sheet_{chunk[0] + 1:02d}-{chunk[-1] + 1:02d}.png")
print(f"rendered pages {first}-{last} of {doc.page_count} to {out}")
