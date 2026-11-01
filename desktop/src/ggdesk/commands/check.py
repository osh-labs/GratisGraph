"""ggdesk check JOB.ggj FILE.m20 [selection flags]: gate existing bytes against a job.

The intent (H10) comes from building the job with the same library and
selection (ggdesk.build.build); the gate then judges FILE's bytes, never the
rebuilt bytes. Prints the text report. Exit 0 pass, 3 refused, 1 error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ggdesk import build as builder
from ggdesk.commands._stub import add_selection_arguments
from ggdesk.commands.selection import UsageError, library_from_args, selection_from_args
from ggdesk.formats import job as jobfile
from ggdesk.gate import run_gate
from ggdesk.library import OverrideError, SelectionError, UnmeasuredError

PASS, ERROR, REFUSED = 0, 1, 3


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("job", type=Path, help="the gratisgraph job (.ggj) the bytes claim to engrave")
    p.add_argument("file", type=Path, help="the .m20 bytes to check")
    add_selection_arguments(p)


def run(args: argparse.Namespace) -> int:
    try:
        sel = selection_from_args(args)
        lib = library_from_args(args)
        text = args.job.read_text(encoding="utf-8")
        job = jobfile.loads(text)
        data = args.file.read_bytes()
        result = builder.build(job, lib, sel, job_text=text)
    except (UsageError, OSError, jobfile.JobFormatError, SelectionError, OverrideError, UnmeasuredError,
            KeyError, builder.BuildError) as e:
        print(f"ggdesk check: {e}", file=sys.stderr)
        return ERROR
    report = run_gate(data, builder.gate_inputs(result, sel))
    sys.stdout.write(report.to_text())
    return PASS if report.passed else REFUSED
