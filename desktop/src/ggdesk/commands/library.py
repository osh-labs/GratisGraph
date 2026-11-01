"""ggdesk library validate: load every entry and list problems (exit 1 if any)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ggdesk import paths
from ggdesk.library import load_library, unmeasured


def add_arguments(p: argparse.ArgumentParser) -> None:
    sub = p.add_subparsers(dest="library_cmd", required=True)
    v = sub.add_parser("validate", help="validate the seed library (and optional extra directories)")
    v.add_argument("--user", type=Path, help="user library directory to validate on top of the seed")
    v.add_argument("--extra", type=Path, action="append", default=[], help="further overlay directory")
    v.add_argument("--unmeasured", action="store_true", help="also list every needs_measurement fact")


def run(args: argparse.Namespace) -> int:
    root = paths.ROOT.parent if not paths.FROZEN else None
    lib = load_library(None, args.user, *args.extra, check_paths=root)
    n = sum(1 for _ in lib.entries())
    for e in lib.errors:
        print(f"ERROR {e}", file=sys.stderr)
    print(f"{n} entries loaded, {len(lib.errors)} error(s)")
    if args.unmeasured:
        for kind, eid, fld, fact in unmeasured(lib):
            print(f"needs_measurement  {kind}:{eid}  {fld}  {fact.gap}")
    return 1 if lib.errors else 0
