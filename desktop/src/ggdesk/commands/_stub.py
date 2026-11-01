"""Shared stub for commands whose slice has not landed in this build."""
from __future__ import annotations

import argparse
import sys

NOT_IMPLEMENTED = 2


def not_implemented(name: str) -> int:
    print(f"ggdesk {name}: not implemented in this build", file=sys.stderr)
    return NOT_IMPLEMENTED


def add_selection_arguments(p: argparse.ArgumentParser) -> None:
    """Selection flags shared by build, check and preview (ggdesk.library.Selection)."""
    p.add_argument("--recipe", help="recipe library id")
    p.add_argument("--fixture", default="bare-bed", help="fixture library id (default bare-bed)")
    p.add_argument("--nest", default="centre", help="nest id within the fixture (default centre)")
    p.add_argument("--machine", default="m20-iq", help="machine library id (default m20-iq)")
    p.add_argument("--set", dest="overrides", action="append", default=[], metavar="KEY=VALUE",
                   help="bench override on a draft recipe (repeatable)")
    p.add_argument("--keep-out", dest="keep_outs", action="append", default=[], metavar="X0,Y0,X1,Y1",
                   help="per-job keep-out rectangle, machine frame mm (fixtures that allow it)")
    p.add_argument("--library", dest="library_dirs", action="append", default=[], type=str,
                   metavar="DIR", help="extra library directory, overrides by id (repeatable)")
