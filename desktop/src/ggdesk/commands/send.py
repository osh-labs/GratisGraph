"""ggdesk send FILE.m20 --report FILE.gate.json --job JOB.ggj [--ack ...] [--operator NAME] [--dry-run]

Refuses without a passing report bound to the file's bytes. Re-runs build and gate from the
report's recorded selection and the job, exactly as `ggdesk build` does, and refuses when the
bytes or the report differ (a stale or edited report). Then connects, checks the machine
entry allows sending, and hands over to the gated send path (`ggdesk.run.Runner`). Ctrl-C
during the run sends the driver's stop (`!1B 0;`) and logs `aborted`.

Exit: 0 completed, 4 unconfirmed or aborted, 3 refused, 1 error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import ggdesk.build as builder
from ggdesk import gate, paths
from ggdesk import run as runmod
from ggdesk.formats import job as job_format
from ggdesk.gate.types import GateReport
from ggdesk.joblog import JobLog
from ggdesk.library import load_library
from ggdesk.library.model import Machine

EXIT_COMPLETED = 0
EXIT_ERROR = 1
EXIT_REFUSED = 3
EXIT_UNCONFIRMED = 4


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("file", type=Path, help="the .m20 bytes to send (as written by ggdesk build)")
    p.add_argument("--report", type=Path, required=True, help="the gate report written next to it (.gate.json)")
    p.add_argument("--job", type=Path, required=True, help="the job file the bytes were built from (.ggj)")
    p.add_argument("--ack", default="", help='typed acknowledgement of soft flags, e.g. "I ACCEPT 3 FLAGS"')
    p.add_argument("--operator", default=None, help="operator name for the job log (optional)")
    p.add_argument("--library", dest="library_dirs", action="append", default=[], type=Path, metavar="DIR",
                   help="extra library directory, as given to ggdesk build (repeatable)")
    p.add_argument("--dry-run", action="store_true", help="every check except connecting and sending")
    p.add_argument("--capture", type=Path, default=None, metavar="FILE.jsonl",
                   help="write every decoded machine packet (telemetry such as !MZ, !CM, !ET) to this file, "
                        "one JSON object per line with a timestamp (bench measurements, e.g. V2)")


class Capture:
    """Driver tap that appends every decoded packet to a JSON-lines file (reader thread)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("a", encoding="utf-8", newline="\n")

    def __call__(self, item: object) -> None:
        rec = {"t": runmod.utc_now_iso(), "item": item}
        self._fh.write(json.dumps(rec, sort_keys=True, default=_jsonable) + "\n")
        self._fh.flush()


def _jsonable(v: object) -> object:
    if isinstance(v, (bytes, bytearray)):
        return v.hex()
    if isinstance(v, tuple):
        return list(v)
    return str(v)


def _refused(reason: str) -> int:
    print(f"ggdesk send: REFUSED: {reason}", file=sys.stderr)
    return EXIT_REFUSED


def _recheck(args: argparse.Namespace, data: bytes, report: GateReport, report_text: str
             ) -> tuple[str | None, Machine | None]:
    """Re-run build and gate from the job and the report's selection. Returns (refusal, machine)."""
    if not report.bound_to(data):
        return f"the report is not bound to {args.file.name} (sha256 or size differs)", None
    if not report.passed:
        return "the gate report did not pass", None
    job_text = args.job.read_text(encoding="utf-8")
    try:
        job = job_format.loads(job_text)
    except job_format.JobFormatError as e:
        return f"job file rejected: {e}", None
    lib = load_library(None, paths.user_library(), *args.library_dirs)
    sel = report.selection
    try:
        result = builder.build(job, lib, sel, job_text=job_text)
    except (builder.BuildError, ValueError, KeyError) as e:
        return f"rebuilding the job failed: {e}", None
    if result.data != data:
        return f"rebuilding the job with the report's selection gives different bytes than {args.file.name}", None
    fresh = gate.run_gate(result.data, builder.gate_inputs(result, sel))
    try:
        stored_obj = json.loads(report_text)
    except ValueError:
        stored_obj = None
    if fresh.to_json() != report.to_json() or json.loads(fresh.to_json()) != stored_obj:
        return "the stored gate report differs from a fresh gate run (stale or edited report)", None
    try:
        machine: Machine = lib.get("machine", sel.machine)
    except KeyError as e:
        return f"machine not in the library: {e.args[0]}", None
    if not machine.send_enabled:
        return f"machine {machine.ref.id} has send_enabled = false in the library", None
    return None, machine


def run(args: argparse.Namespace) -> int:
    log = None if args.dry_run else JobLog()
    try:
        data = args.file.read_bytes()
        report_text = args.report.read_text(encoding="utf-8")
        report = GateReport.from_json(report_text)
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"ggdesk send: cannot read the job bytes or the report: {e}", file=sys.stderr)
        return EXIT_ERROR
    try:
        reason, machine = _recheck(args, data, report, report_text)
    except OSError as e:
        print(f"ggdesk send: {e}", file=sys.stderr)
        return EXIT_ERROR
    if reason is not None:
        if log is not None:
            now = runmod.utc_now_iso()
            log.append(runmod.log_record("refused", data, report, ack=args.ack, started=now, ended=now,
                                      operator=args.operator, reason=reason))
        return _refused(reason)

    if args.dry_run:
        reason = runmod.preflight(data, report, args.ack, machine, None)
        if reason is not None:
            return _refused(reason)
        print("ggdesk send: dry run: every check passed; not connecting, nothing sent.")
        return EXIT_COMPLETED

    assert log is not None
    conn = runmod.open_connection()
    try:
        if not conn.connect():
            print("ggdesk send: machine not found (USB)", file=sys.stderr)
            return EXIT_ERROR
        if args.capture is not None:
            conn.add_tap(Capture(args.capture))
        runner = runmod.Runner(conn, log, machine=machine)
        try:
            result = runner.send_gated(data, report, args.ack, operator=args.operator)
        except runmod.SendRefused as e:
            return _refused(str(e))
        except Exception as e:
            print(f"ggdesk send: error during the run: {e}", file=sys.stderr)
            return EXIT_ERROR
    finally:
        try:
            conn.disconnect()
        except Exception as e:   # releasing the device must not mask the run's outcome
            print(f"ggdesk send: disconnect: {e}", file=sys.stderr)
    msg = {"completed": f"completed (!ET {result.et})",
           "unconfirmed": "UNCONFIRMED: no !ET after !CM 1; check the machine",
           "aborted": "ABORTED: stop sent (!1B 0;)"}[result.status]
    print(f"ggdesk send: {msg}")
    return EXIT_COMPLETED if result.status == "completed" else EXIT_UNCONFIRMED
