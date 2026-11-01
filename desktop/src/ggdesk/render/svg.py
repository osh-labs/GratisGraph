"""SVG from a DrawList: deterministic text, same items as the on-screen preview.

The viewBox is in machine mm with +Y down (see drawlist.py), so polyline
points are the draw list's points unchanged. Every item becomes one element
carrying `data-kind`; a `start` item is a circle, everything else a polyline.
Numbers are printed with `fmt_mm` (shortest repr of the value rounded to
0.0001 mm via string formatting, which is correctly rounded on every
platform), so the text is identical on Linux and Windows.

The SVG has its own print palette here: the core cannot import the GUI theme
(ggdesk_app/theme.py), and the SVG is a document, not the themed window.
"""
from __future__ import annotations

from ggdesk.render.drawlist import OPERATOR_LABEL, DrawList

# Print palette (light background); kinds match drawlist.KINDS.
SVG_STYLE: dict[str, str] = {
    "field": "fill:none;stroke:#6b7280;stroke-width:0.3;stroke-dasharray:2 1",
    "part": "fill:#e5e7eb;stroke:#374151;stroke-width:0.25",
    "keep_out": "fill:#fca5a5;fill-opacity:0.5;stroke:#b91c1c;stroke-width:0.25",
    "rapid": "fill:none;stroke:#2563eb;stroke-width:0.15;stroke-dasharray:1 0.6",
    "cut": "fill:none;stroke:#111827;stroke-width:0.3;stroke-linejoin:round;stroke-linecap:round",
    "start": "fill:#16a34a;stroke:none",
    "label": "fill:#374151;font-family:sans-serif;font-size:3px",
}
START_RADIUS_MM = 0.8
MARGIN_MM = 6.0


def fmt_mm(v: float) -> str:
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _pts(points: tuple[tuple[float, float], ...]) -> str:
    return " ".join(f"{fmt_mm(x)},{fmt_mm(y)}" for x, y in points)


def to_svg(dl: DrawList, px_per_mm: float = 5.0) -> str:
    x0, y0, x1, y1 = dl.bounds()
    x0, y0, x1, y1 = x0 - MARGIN_MM, y0 - MARGIN_MM, x1 + MARGIN_MM, y1 + MARGIN_MM
    w, h = x1 - x0, y1 - y0
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{fmt_mm(w * px_per_mm)}" '
        f'height="{fmt_mm(h * px_per_mm)}" viewBox="{fmt_mm(x0)} {fmt_mm(y0)} {fmt_mm(w)} {fmt_mm(h)}">',
        "<!-- GratisGraph Desktop preview from decoded .m20 bytes. Machine frame, mm: home (0,0) back-left, "
        "+X right, +Y toward the operator (drawn down). -->",
        "<style>",
        *(f".{k.replace('_', '-')} {{{v}}}" for k, v in SVG_STYLE.items()),
        "</style>",
    ]
    for item in dl.items:
        cls = item.kind.replace("_", "-")
        if item.kind == "start":
            x, y = item.points[0]
            out.append(f'<circle class="{cls}" data-kind="{item.kind}" cx="{fmt_mm(x)}" cy="{fmt_mm(y)}" '
                       f'r="{fmt_mm(START_RADIUS_MM)}"/>')
        else:
            out.append(f'<polyline class="{cls}" data-kind="{item.kind}" points="{_pts(item.points)}"/>')
    cx = (dl.bounds()[0] + dl.bounds()[2]) / 2
    out.append(f'<text class="label" x="{fmt_mm(cx)}" y="{fmt_mm(y1 - MARGIN_MM / 3)}" '
               f'text-anchor="middle">{OPERATOR_LABEL}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"
