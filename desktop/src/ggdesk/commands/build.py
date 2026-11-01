"""ggdesk build JOB.ggj -o OUT.m20 [selection flags]: build, then gate the final bytes.

Writes OUT.m20, OUT.gate.json and OUT.gate.txt and prints the text report.
Exit 0 when the gate passes (soft flags still need acknowledgement at send),
3 when it refuses, 1 on a build error, 2 on a usage error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ggdesk.build import BuildError, build, gate_inputs
from ggdesk.commands._stub import add_selection_arguments
from ggdesk.commands.selection import UsageError, library_from_args, selection_from_args
from ggdesk.formats import job as job_format
from ggdesk.gate import run_gate

EXIT_PASS = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_REFUSED = 3


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("job", type=Path, help="job file (.ggj)")
    p.add_argument("-o", "--output", type=Path, required=True, help="output .m20 file")
    add_selection_arguments(p)


def report_paths(out: Path) -> tuple[Path, Path]:
    """OUT.m20 -> (OUT.gate.json, OUT.gate.txt)."""
    stem = out.with_suffix("") if out.suffix else out
    return stem.with_name(stem.name + ".gate.json"), stem.with_name(stem.name + ".gate.txt")


def run(args: argparse.Namespace) -> int:
    try:
        sel = selection_from_args(args)
    except UsageError as e:
        print(f"ggdesk build: {e}", file=sys.stderr)
        return EXIT_USAGE
    try:
        text = Path(args.job).read_text(encoding="utf-8")
    except OSError as e:
        print(f"ggdesk build: cannot read {args.job}: {e}", file=sys.stderr)
        return EXIT_ERROR
    try:
        job = job_format.loads(text)
    except job_format.JobFormatError as e:
        print(f"ggdesk build: {args.job}: {e}", file=sys.stderr)
        return EXIT_ERROR
    lib = library_from_args(args)
    for err in lib.errors:
        print(f"ggdesk build: library entry skipped: {err.path}: {err.message}", file=sys.stderr)
    try:
        result = build(job, lib, sel, job_text=text)
    except BuildError as e:
        print(f"ggdesk build: {e}", file=sys.stderr)
        return EXIT_ERROR

    out = Path(args.output)
    out.write_bytes(result.data)
    report = run_gate(result.data, gate_inputs(result, sel))
    json_path, txt_path = report_paths(out)
    json_path.write_text(report.to_json(), encoding="utf-8", newline="\n")
    txt = report.to_text()
    txt_path.write_text(txt, encoding="utf-8", newline="\n")
    print(f"wrote {out} ({len(result.data)} bytes), {json_path.name}, {txt_path.name}")
    if result.dropped_points:
        print(f"note: {result.dropped_points} path(s) collapsed to one point at 0.01 mm and were dropped")
    sys.stdout.write(txt)
    return EXIT_PASS if report.passed else EXIT_REFUSED
