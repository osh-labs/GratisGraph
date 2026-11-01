"""ggdesk preview FILE.m20 -o OUT.svg [--job JOB.ggj + selection flags] (m1-plan 2.8).

Renders the DECODED bytes. With --job (and --recipe) it also draws the work
field, the part outline at its placement and the keep-outs from the library.
Exit 0 written; 1 the bytes do not decode or the job/selection is rejected;
2 usage error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ggdesk.commands._stub import add_selection_arguments
from ggdesk.commands.selection import UsageError, library_from_args, selection_from_args
from ggdesk.formats import job as job_format
from ggdesk.gts_read import GtsFormatError
from ggdesk.library import OverrideError, Resolved, SelectionError, resolve
from ggdesk.render import draw_list, to_svg


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("file", type=Path, help=".m20 job bytes to render")
    p.add_argument("-o", "--output", type=Path, required=True, help="SVG file to write")
    p.add_argument("--job", type=Path, help="job file (.ggj): adds field, part outline and keep-outs")
    p.add_argument("--px-per-mm", type=float, default=5.0, help="SVG size scale (default 5)")
    add_selection_arguments(p)


def _resolved(args: argparse.Namespace) -> Resolved | None:
    if args.job is None:
        return None
    job = job_format.load(args.job)
    return resolve(library_from_args(args), job, selection_from_args(args))


def run(args: argparse.Namespace) -> int:
    try:
        resolved = _resolved(args)
    except UsageError as e:
        print(f"ggdesk preview: {e}", file=sys.stderr)
        return 2
    except (job_format.JobFormatError, SelectionError, OverrideError, KeyError, OSError) as e:
        print(f"ggdesk preview: {e}", file=sys.stderr)
        return 1
    try:
        data = args.file.read_bytes()
        dl = draw_list(data, resolved)
    except (GtsFormatError, OSError) as e:
        print(f"ggdesk preview: {args.file}: {e}", file=sys.stderr)
        return 1
    args.output.write_bytes(to_svg(dl, args.px_per_mm).encode("utf-8"))
    cuts = len(dl.of_kind("cut"))
    print(f"wrote {args.output} ({cuts} cut path{'s' if cuts != 1 else ''}, {len(dl.items)} items)")
    return 0
