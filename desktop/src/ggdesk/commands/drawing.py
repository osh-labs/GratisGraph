"""ggdesk drawing nest --part P --fixture F -o OUT: nest plate drawing as OUT.svg and OUT.dxf.

Prints the unmeasured list. Exit 0 when written; with --require-measured, 3 (and nothing written)
when any dimension is drawn from a placeholder; 1 on a library or geometry error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ggdesk.commands.selection import library_from_args
from ggdesk.drawings.nest import (
    DEFAULT_PLATE_MARGIN_MM,
    DEFAULT_POCKET_CLEARANCE_MM,
    NOT_FOR_CUTTING,
    NestDrawingError,
    nest_plate,
)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_UNMEASURED = 3


def add_arguments(p: argparse.ArgumentParser) -> None:
    sub = p.add_subparsers(dest="drawing_cmd", required=True)
    n = sub.add_parser("nest", help="nest plate for one blank (SVG and DXF R12)")
    n.add_argument("--part", required=True, help="part library id")
    n.add_argument("--fixture", required=True, help="fixture library id")
    n.add_argument("--nest", default="centre", help="nest id within the fixture (default centre)")
    n.add_argument("-o", "--output", type=Path, required=True, help="output stem: writes OUT.svg and OUT.dxf")
    n.add_argument("--margin", type=float, default=DEFAULT_PLATE_MARGIN_MM,
                   help=f"plate margin around the pocket, mm (design choice, default {DEFAULT_PLATE_MARGIN_MM})")
    n.add_argument("--clearance", type=float, default=DEFAULT_POCKET_CLEARANCE_MM,
                   help="pocket clearance per side, mm (design choice, default "
                        f"{DEFAULT_POCKET_CLEARANCE_MM})")
    n.add_argument("--require-measured", action="store_true",
                   help="exit 3 and write nothing if any dimension is unmeasured")
    n.add_argument("--library", dest="library_dirs", action="append", default=[], type=str, metavar="DIR",
                   help="extra library directory, overrides by id (repeatable)")


def output_paths(out: Path) -> tuple[Path, Path]:
    """OUT, OUT.svg or OUT.dxf -> (OUT.svg, OUT.dxf)."""
    stem = out.with_suffix("") if out.suffix.lower() in (".svg", ".dxf") else out
    return stem.with_name(stem.name + ".svg"), stem.with_name(stem.name + ".dxf")


def run(args: argparse.Namespace) -> int:
    lib = library_from_args(args)
    for err in lib.errors:
        print(f"ggdesk drawing: library entry skipped: {err.path}: {err.message}", file=sys.stderr)
    try:
        part = lib.get("part", args.part)
        fixture = lib.get("fixture", args.fixture)
        d = nest_plate(part, fixture, nest_id=args.nest, plate_margin_mm=args.margin,
                       pocket_clearance_mm=args.clearance)
    except (KeyError, NestDrawingError) as e:
        msg = e.args[0] if isinstance(e, KeyError) and e.args else e
        print(f"ggdesk drawing: {msg}", file=sys.stderr)
        return EXIT_ERROR
    for u in d.unmeasured:
        print(f"UNMEASURED  {u}")
    if d.unmeasured and args.require_measured:
        print(f"ggdesk drawing: {len(d.unmeasured)} unmeasured item(s); nothing written (--require-measured)",
              file=sys.stderr)
        return EXIT_UNMEASURED
    svg, dxf = output_paths(Path(args.output))
    svg.write_text(d.svg, encoding="utf-8", newline="\n")
    dxf.write_text(d.dxf, encoding="ascii", newline="\n")
    print(f"wrote {svg} and {dxf} (plate {d.plate_mm[0]:.2f} x {d.plate_mm[1]:.2f} mm)")
    print(NOT_FOR_CUTTING if d.unmeasured else "all dimensions from library facts")
    return EXIT_OK
