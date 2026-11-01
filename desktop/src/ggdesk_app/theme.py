"""Every colour the GUI uses, and nothing else decides one.

Panels ask this module for a QColor or a stylesheet fragment by role; a test
fails if a colour literal appears anywhere else in ggdesk_app. Sizes are
relative (cosmetic pens, the application font), so the window reads the same
at 100 % and 150 % display scaling.
"""
from __future__ import annotations

from PySide6.QtGui import QColor

# Preview: one entry per render.drawlist kind, plus the background and the operator label.
PREVIEW: dict[str, str] = {
    "background": "#f8fafc",
    "field": "#6b7280",
    "part": "#374151",
    "part_fill": "#e5e7eb",
    "keep_out": "#b91c1c",
    "keep_out_fill": "#fca5a5",
    "rapid": "#2563eb",
    "cut": "#111827",
    "start": "#16a34a",
    "label": "#374151",
}

# Gate report and status line.
STATUS: dict[str, str] = {
    "hard": "#b91c1c",
    "soft": "#b45309",
    "pass": "#15803d",
    "error": "#b91c1c",
    "muted": "#4b5563",
}

# Pen widths in device pixels (cosmetic: they do not scale with zoom).
PEN_PX: dict[str, float] = {"field": 1.0, "part": 1.0, "keep_out": 1.0, "rapid": 1.0, "cut": 1.6}
KEEP_OUT_FILL_ALPHA = 110      # 0..255
START_RADIUS_MM = 0.8


def colour(role: str) -> QColor:
    """A preview colour by role (KeyError for an unknown role)."""
    return QColor(PREVIEW[role])


def status_colour(role: str) -> QColor:
    return QColor(STATUS[role])


def text_style(role: str, bold: bool = False) -> str:
    """Stylesheet fragment for a label in a status role."""
    return f"color: {STATUS[role]};" + (" font-weight: bold;" if bold else "")
