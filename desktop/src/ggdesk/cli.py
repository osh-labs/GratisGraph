"""ggdesk command line. Every core operation is reachable from here.

  ggdesk check | build | preview | send | pattern | library validate | inspect | version

This module only parses arguments and dispatches to ggdesk.commands.<name>.run.
Each slice owns its command module (desktop/docs/m1-plan.md section 2.8).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import sys
from collections.abc import Sequence
from pathlib import Path

from ggdesk import __version__
from ggdesk.gts_read import Command, GtsFormatError, read_job
from ggdesk.numerics import to_mm

COMMANDS = {
    "check": "gate existing .m20 bytes against a job and the library",
    "build": "job + recipe + fixture -> .m20, then gate it",
    "preview": "render an .m20 (decoded bytes) as SVG",
    "send": "send gated bytes to the machine (refuses without a bound, passing report)",
    "pattern": "generate a bench test pattern job",
    "library": "library tools (validate)",
}


def _extent(points: list[tuple[int, int]]) -> str:
    if not points:
        return "none"
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (f"X {to_mm(min(xs)):.2f}..{to_mm(max(xs)):.2f}  "
            f"Y {to_mm(min(ys)):.2f}..{to_mm(max(ys)):.2f}")


def _inspect(path: Path) -> int:
    data = path.read_bytes()
    try:
        job = read_job(data)
    except GtsFormatError as e:
        print(f"{path}: not a valid GTS job: {e}", file=sys.stderr)
        return 1
    pos = job.positions()
    cut = job.cut_points()
    pd = sum(1 for c in job.commands if c.op == "PD")
    jf = [c for c in job.commands if c.op == "JF"]
    print(f"file        {path}")
    print(f"bytes       {len(data)}")
    print(f"sha256      {hashlib.sha256(data).hexdigest()}")
    print(f"model code  0x{job.model_code:04X} (stamped at send time by the driver)")
    print("setup       " + " ".join(f"{op} {arg}" for op, arg in job.setup()))
    print(f"strokes     {pd}")
    print(f"cut mm      {_extent(cut)}")
    print(f"travel mm   {_extent(pos)}  (includes rapids and the return home)")
    print(f"ends home   {'yes' if pos and pos[-1] == (0, 0) else 'NO'}")
    last = job.records[-1] if job.records else None
    jf_ok = len(jf) == 1 and isinstance(last, Command) and last.op == "JF"
    print(f"JF          {len(jf)} ({'final record' if jf_ok else 'NOT a single final JF'})")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ggdesk", description="GratisGraph Desktop core")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("version", help="print the version")
    p = sub.add_parser("inspect", help="decode an .m20 job and summarise it")
    p.add_argument("file", type=Path)
    for name, help_text in COMMANDS.items():
        mod = importlib.import_module(f"ggdesk.commands.{name}")
        mod.add_arguments(sub.add_parser(name, help=help_text))
    args = ap.parse_args(argv)
    if args.cmd == "version":
        print(f"ggdesk {__version__}")
        return 0
    if args.cmd == "inspect":
        return _inspect(args.file)
    mod = importlib.import_module(f"ggdesk.commands.{args.cmd}")
    rc: int = mod.run(args)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
