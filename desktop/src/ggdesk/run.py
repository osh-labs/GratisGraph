"""The gated send path: the only code in the app that hands bytes to the driver.

desktop/docs/m1-plan.md section 2.6. `Runner.send_gated` refuses (raises `SendRefused` and
writes a job-log record) unless every condition holds:

  * the gate report is bound to these exact bytes (SHA-256 and size) and passed;
  * the soft flags are acknowledged with the exact phrase (`I ACCEPT 3 FLAGS`);
  * the machine entry allows sending and is the one the report was gated for;
  * the connection is connected and identified (`!ID` model code non-zero);
  * header model code (0x24) == report model code == connected model code, so the driver's
    re-stamp is a no-op and the bytes sent are the bytes gated;
  * the driver's home job, stamped with that model code, passes `gate.home.check_home_job`
    (absent check = refusal, never a silent skip);
  * no other job is in flight (queue of one in M1).

Only then `send_gts(data, home_first=True)`. Completion comes from the driver's IQ monitor,
observed through a tap: `completed` when an `!ET` follows `!CM 4;` = 1, `aborted` when
`abort()` was called during the run, else `unconfirmed`.
"""
from __future__ import annotations

import hashlib
import importlib
import struct
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from ggdesk import __version__
from ggdesk.gate.types import GateReport, Severity, acknowledged
from ggdesk.joblog import JobLog
from ggdesk.library.model import Machine

GTS_MAGIC = b"!MM88;"          # gts_api.MAGIC
MODEL_CODE_OFFSET = 0x24       # gts_api.GTSConnection._stamp_model_code
Status = Literal["completed", "unconfirmed", "aborted"]


class Connection(Protocol):
    """What the Runner needs from `gts_api.GTSConnection` (FakeConn in tests)."""

    model_code: int
    dev: object | None

    def connect(self, timeout_s: float = 5.0, wait: bool = False) -> bool: ...
    def add_tap(self, fn: Callable[[Any], None]) -> None: ...
    def send_gts(self, gts: bytes, home_first: bool = True) -> None: ...   # blocks in the driver's monitor
    def abort(self) -> None: ...
    def disconnect(self) -> None: ...


class SendRefused(RuntimeError):
    """A send precondition failed; nothing was written to the machine."""


@dataclass(frozen=True)
class RunResult:
    status: Status
    et: int | None
    started: str
    ended: str


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def header_model_code(data: bytes) -> int | None:
    """Model code at header 0x24, or None when the bytes are not a GTS job."""
    if not data.startswith(GTS_MAGIC) or len(data) < MODEL_CODE_OFFSET + 2:
        return None
    code: int = struct.unpack_from(">H", data, MODEL_CODE_OFFSET)[0]
    return code


def stamp_model_code(gts: bytes, model_code: int) -> bytes:
    """Exactly what `GTSConnection._stamp_model_code` does with the identified model code."""
    if not model_code or not gts.startswith(GTS_MAGIC) or len(gts) < MODEL_CODE_OFFSET + 2:
        return gts
    b = bytearray(gts)
    struct.pack_into(">H", b, MODEL_CODE_OFFSET, model_code)
    return bytes(b)


def home_job_bytes(model_code: int) -> bytes:
    """The home job the driver queues before each job with `home_first=True`, as sent."""
    import gts_api

    home: bytes = gts_api.build_home_gts()
    return stamp_model_code(home, model_code)


def _home_check() -> Callable[[bytes, Machine], GateReport] | None:
    """gate.home.check_home_job (slice M1.2), imported lazily; None when unavailable."""
    try:
        mod = importlib.import_module("ggdesk.gate.home")
    except ImportError:
        return None
    fn = getattr(mod, "check_home_job", None)
    return fn if callable(fn) else None


def report_summary(report: GateReport | None) -> dict[str, Any] | None:
    if report is None:
        return None
    return {
        "passed": report.passed, "flags": report.flags,
        "findings": [f.rule for f in report.findings],
        "hard": sorted({f.rule for f in report.findings if f.severity is Severity.HARD}),
        "entries": [{"kind": e.kind, "id": e.id, "version": e.version, "sha256": e.sha256}
                    for e in report.entries],
        "selection": report.selection.to_obj(),
        "app_version": report.app_version,
    }


def log_record(event: str, data: bytes, report: GateReport | None, *, ack: str = "",
               started: str, ended: str | None = None, operator: str | None = None,
               connected_model_code: int | None = None, reason: str | None = None,
               et: int | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """One job-log record. The typed acknowledgement is logged only as a boolean."""
    rec: dict[str, Any] = {
        "event": event, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
        "report": report_summary(report), "ack_given": bool(ack.strip()),
        "model_code": header_model_code(data), "connected_model_code": connected_model_code,
        "started": started, "ended": ended, "et": et, "operator": operator,
        "app_version": __version__,
    }
    if reason is not None:
        rec["reason"] = reason
    if extra:
        rec.update(extra)
    return rec


def _hex(code: int | None) -> str:
    return "none" if code is None else f"0x{code:04X}"


def preflight(data: bytes, report: GateReport, ack: str, machine: Machine | None,
              conn: Connection | None) -> str | None:
    """The refusal reason, or None when every send condition holds.

    conn=None checks everything that does not need a machine (`ggdesk send --dry-run`); the
    model codes are then compared with the library's instead of the connected machine's.
    """
    if not report.bound_to(data):
        return (f"the gate report is not bound to these bytes (report sha256 {report.sha256[:12]}..., "
                f"{report.size} bytes; file sha256 {hashlib.sha256(data).hexdigest()[:12]}..., {len(data)} bytes)")
    if not report.passed:
        hard = ", ".join(sorted({f.rule for f in report.findings if f.severity is Severity.HARD}))
        return f"the gate refused this job (hard findings: {hard})"
    if not acknowledged(report, ack):
        return (f"{report.flags} soft flag(s) need acknowledgement: type exactly '{report.ack_phrase}'"
                if ack.strip() else f"{report.flags} soft flag(s) not acknowledged: type '{report.ack_phrase}'")
    if machine is None:
        return "no machine library entry was given, so the home job cannot be checked"
    if not machine.send_enabled:
        return f"machine {machine.ref.id} has send_enabled = false in the library"
    if report.selection.machine != machine.ref.id:
        return f"the report was gated for machine {report.selection.machine}, not {machine.ref.id}"
    if conn is not None:
        if conn.dev is None:
            return "the machine is not connected"
        if not conn.model_code:
            return "the connected machine has not identified itself (no !ID model code)"
        target = conn.model_code
    elif machine.model_code.known and machine.model_code.value:
        target = int(machine.model_code.value)
    else:
        return f"machine {machine.ref.id} model code is unknown in the library"
    header = header_model_code(data)
    if header is None or header != report.model_code or header != target:
        who = "connected machine" if conn is not None else "library machine"
        return (f"model code mismatch: header {_hex(header)}, report {_hex(report.model_code)}, "
                f"{who} {_hex(target)} (the driver would re-stamp and send bytes the gate did not check)")
    if machine.model_code.known and machine.model_code.value != target:
        return (f"model code mismatch: library {machine.ref.id} is {_hex(machine.model_code.value)}, "
                f"target {_hex(target)}")
    check = _home_check()
    if check is None:
        return "the home-job check (ggdesk.gate.home.check_home_job) is not available in this build"
    home = check(home_job_bytes(target), machine)
    if not home.passed or home.flags:
        rules = ", ".join(f.rule for f in home.findings) or "none"
        return f"the driver's home job failed its gate check (findings: {rules})"
    return None


class Runner:
    """Sends one gated job at a time and logs every attempt."""

    def __init__(self, conn: Connection, log: JobLog, clock: Callable[[], str] = utc_now_iso, *,
                 machine: Machine | None = None, settle_s: float = 1.0) -> None:
        self.conn = conn
        self.log = log
        self.clock = clock
        self.machine = machine
        self.settle_s = settle_s   # wait after send_gts returns for the tap to see the !ET it returned on
        self._lock = threading.Lock()
        self._in_flight = False
        self._abort_requested = False
        self._cm: list[int | None] = []
        self._cm1_seen = False
        self._et: int | None = None
        self._jf = 0
        self._et_event = threading.Event()
        conn.add_tap(self._on_packet)

    @property
    def in_flight(self) -> bool:
        return self._in_flight

    def _on_packet(self, item: Any) -> None:
        """Driver tap (reader thread). Shapes from gts_api._parse_rx_buf: {'type': 'ack', 'cmd': '!CM 4;',
        'value': uint32, 'values': (int32,), ...}; !ET 4; likewise; !JF 0; with value None."""
        if not isinstance(item, dict) or item.get("type") != "ack":
            return
        cmd = str(item.get("cmd", ""))
        with self._lock:
            if not self._in_flight:
                return
            if cmd.startswith("!JF"):
                self._jf += 1
            elif cmd.startswith("!CM"):
                v = (item.get("values") or (None,))[0]
                self._cm.append(v)
                if v == 1:
                    self._cm1_seen = True
            elif cmd.startswith("!ET") and self._cm1_seen and self._et is None:
                value = item.get("value")
                self._et = int(value) if value is not None else None
                self._et_event.set()

    def _refuse(self, data: bytes, report: GateReport, ack: str, reason: str, operator: str | None) -> SendRefused:
        now = self.clock()
        code = getattr(self.conn, "model_code", None)
        self.log.append(log_record("refused", data, report, ack=ack, started=now, ended=now, operator=operator,
                                   connected_model_code=code or None, reason=reason))
        return SendRefused(reason)

    def send_gated(self, data: bytes, report: GateReport, ack: str = "", *,
                   operator: str | None = None) -> RunResult:
        data = bytes(data)
        reason = preflight(data, report, ack, self.machine, self.conn)
        if reason is not None:
            raise self._refuse(data, report, ack, reason, operator)
        with self._lock:
            busy = self._in_flight
            if not busy:
                self._in_flight = True
                self._abort_requested = False
                self._cm, self._cm1_seen, self._et, self._jf = [], False, None, 0
                self._et_event.clear()
        if busy:
            raise self._refuse(data, report, ack, "a job is already in flight (queue of one)", operator)

        code = self.conn.model_code
        started = self.clock()
        self.log.append(log_record("sent", data, report, ack=ack, started=started, operator=operator,
                                   connected_model_code=code))
        error: BaseException | None = None
        interrupted = False
        try:
            self.conn.send_gts(data, home_first=True)
        except KeyboardInterrupt:   # Ctrl-C in the CLI: stop the machine, then report aborted
            interrupted = True
            try:
                self.abort()
            except Exception as e:   # the stop itself failed; logged, the run still ends aborted
                error = e
        except Exception as e:
            error = e
        if not interrupted and error is None:
            self._et_event.wait(self.settle_s)
        with self._lock:
            self._in_flight = False
            et, cm, jf, aborted = self._et, list(self._cm), self._jf, self._abort_requested or interrupted
        ended = self.clock()
        status: Status = "aborted" if aborted else ("completed" if et is not None else "unconfirmed")
        extra: dict[str, Any] = {"cm": cm, "jf": jf}
        if error is not None:
            extra["error"] = f"{type(error).__name__}: {error}"
        self.log.append(log_record(status, data, report, ack=ack, started=started, ended=ended, operator=operator,
                                   connected_model_code=code, et=et, extra=extra))
        if error is not None and not interrupted:
            raise error
        return RunResult(status, et, started, ended)

    def abort(self) -> None:
        """Emergency stop (`!1B 0;` through the driver). Marks a running job aborted."""
        with self._lock:
            if self._in_flight:
                self._abort_requested = True
        self.conn.abort()


def open_connection() -> Connection:
    """A real, not yet connected GTSConnection (USB). Never used by tests."""
    import gts_api

    conn: Connection = gts_api.GTSConnection(verbose=True)
    return conn
