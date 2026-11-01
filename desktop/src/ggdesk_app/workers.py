"""Background work for the bench window (m1-plan section 3).

BuildWorker: one thread, debounced (about 150 ms), latest wins. Each run
builds and gates through a scratch BenchSession (so BenchSession stays the
only caller of the core) on a snapshot of the job and selection; the result is
handed back to the UI thread and adopted with `session.apply_build`, which
drops it if the job or selection changed meanwhile. A queued request that is
already superseded is skipped before it starts. An unexpected exception
becomes a visible error in the session (and a traceback on stderr); it is
never swallowed.

SendWorker: `session.send` on its own thread, because the driver's send
blocks in its monitor. Abort stays on the UI thread (`session.abort`).
"""
from __future__ import annotations

import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, Qt, QTimer, Signal

from ggdesk.gate import GateReport
from ggdesk.library import Selection
from ggdesk.model.job import Job
from ggdesk_app.session import BenchSession

DEBOUNCE_MS = 150


@dataclass(frozen=True)
class BuildOutcome:
    generation: int
    job: Job
    selection: Selection
    data: bytes | None
    report: GateReport | None
    error: str | None
    status: str


def build_snapshot(session: BenchSession, job: Job, selection: Selection, job_sha256: str | None) -> BuildOutcome:
    """Build and gate one snapshot on a scratch session (any thread). Generation 0; the caller sets it."""
    scratch = BenchSession(library=session.library, runner_factory=_no_runner)
    scratch.state.job = job
    scratch.state.job_sha256 = job_sha256
    scratch.state.selection = selection
    scratch.build_and_gate()
    st = scratch.state
    return BuildOutcome(0, job, selection, st.data, st.report, st.error, st.status)


def _no_runner() -> Any:
    raise RuntimeError("a scratch session never sends")


class BuildWorker(QObject):
    _result = Signal(object)          # BuildOutcome, emitted from the worker thread
    applied = Signal(object)          # BuildOutcome adopted by the session (UI thread)
    dropped = Signal(int)             # generation of a stale result that was discarded

    def __init__(self, session: BenchSession, debounce_ms: int = DEBOUNCE_MS,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self._gen = 0
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ggdesk-build")
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(debounce_ms)
        self._timer.timeout.connect(self._start)
        self._result.connect(self._deliver, Qt.ConnectionType.QueuedConnection)
        self.runs = 0                     # builds actually started (for tests and diagnostics)

    @property
    def generation(self) -> int:
        return self._gen

    def request(self) -> None:
        """Ask for a build of the session's current job and selection; bursts collapse into one."""
        self._timer.start()

    def _start(self) -> None:
        st = self.session.state
        self._gen += 1
        if st.job is None:
            return
        self.session.note("Building and gating...")
        self._pool.submit(self._run, self._gen, st.job, st.selection, st.job_sha256)

    def _run(self, gen: int, job: Job, selection: Selection, job_sha256: str | None) -> None:
        if gen != self._gen:              # superseded while queued
            self._result.emit(BuildOutcome(gen, job, selection, None, None, None, ""))
            return
        self.runs += 1
        try:
            out = build_snapshot(self.session, job, selection, job_sha256)
            out = BuildOutcome(gen, out.job, out.selection, out.data, out.report, out.error, out.status)
        except Exception as e:  # shown to the operator, never swallowed
            traceback.print_exc(file=sys.stderr)
            out = BuildOutcome(gen, job, selection, None, None, f"{type(e).__name__}: {e}",
                               "Build failed with an internal error.")
        self._result.emit(out)

    def _deliver(self, out: BuildOutcome) -> None:
        if out.generation != self._gen or not self.session.apply_build(
                out.job, out.selection, out.data, out.report, out.error, out.status):
            self.dropped.emit(out.generation)
            return
        self.applied.emit(out)

    def shutdown(self) -> None:
        self._timer.stop()
        self._gen += 1
        self._pool.shutdown(wait=False, cancel_futures=True)


class SendWorker(QObject):
    _done = Signal(object, object)    # (RunResult | None, error text | None), from the send thread
    finished = Signal(object, object)  # same, on the UI thread

    def __init__(self, session: BenchSession, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self.busy = False
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ggdesk-send")
        self._done.connect(self._deliver, Qt.ConnectionType.QueuedConnection)

    def start(self, typed_ack: str, operator: str = "") -> bool:
        if self.busy:
            return False
        self.busy = True
        self._pool.submit(self._run, typed_ack, operator)
        return True

    def _run(self, typed_ack: str, operator: str) -> None:
        try:
            result = self.session.send(typed_ack, operator)
        except Exception as e:  # shown to the operator, never swallowed
            traceback.print_exc(file=sys.stderr)
            self._done.emit(None, f"{type(e).__name__}: {e}")
            return
        self._done.emit(result, None)

    def _deliver(self, result: Any, error: str | None) -> None:
        self.busy = False
        self.session.note(run_status(result) if error is None else f"Send failed: {error}")
        self.finished.emit(result, error)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


def run_status(result: Any) -> str:
    """Status line text for a ggdesk.run.RunResult."""
    status = getattr(result, "status", None)
    et = getattr(result, "et", None)
    if status == "completed":
        return "Run completed" + (f" (machine time {et} s)." if et is not None else ".")
    if status == "aborted":
        return "Run aborted."
    if status == "unconfirmed":
        return "Job sent; the machine did not confirm completion. Check the part before the next job."
    return f"Send finished: {status or 'no result'}."
