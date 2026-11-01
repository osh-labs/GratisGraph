"""BenchSession: the only object in the GUI that calls the core.

Panels read its state and call its methods; they never build, gate or send
themselves. M1.0 defines the surface; M1.4 runs build and gate on a worker and
M1.3's Runner does the sending.
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ggdesk.formats import job as job_format
from ggdesk.gate import GateReport, acknowledged
from ggdesk.library import Library, Selection, load_library
from ggdesk.model.job import Job


@dataclass
class SessionState:
    job_path: Path | None = None
    job: Job | None = None
    job_sha256: str | None = None
    selection: Selection = field(default_factory=Selection)
    data: bytes | None = None           # final bytes, model code stamped
    report: GateReport | None = None
    error: str | None = None            # last build or load error, shown to the operator
    status: str = "No job loaded."


class BenchSession:
    def __init__(self, library: Library | None = None) -> None:
        self.library = library if library is not None else load_library()
        self.state = SessionState()
        self._listeners: list[Callable[[SessionState], None]] = []

    def subscribe(self, fn: Callable[[SessionState], None]) -> None:
        self._listeners.append(fn)

    def _changed(self) -> None:
        for fn in list(self._listeners):
            fn(self.state)

    def open_job(self, path: Path) -> None:
        text = Path(path).read_text(encoding="utf-8")
        try:
            job = job_format.loads(text)
        except job_format.JobFormatError as e:
            self.state = SessionState(job_path=Path(path), error=str(e), status="Job file rejected.",
                                      selection=self.state.selection)
            self._changed()
            return
        self.state = SessionState(job_path=Path(path), job=job,
                                  job_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                                  selection=self.state.selection, status=f"Opened {Path(path).name}.")
        self._changed()

    def select(self, selection: Selection) -> None:
        self.state.selection = selection
        self.state.data = None
        self.state.report = None
        self._changed()

    def build_and_gate(self) -> None:
        """Build then gate (M1.1 + M1.2). M1.4 moves this onto a background worker."""
        from ggdesk import gate
        from ggdesk.build import BuildError, build, gate_inputs

        st = self.state
        if st.job is None:
            return
        try:
            result = build(st.job, self.library, st.selection)
        except (BuildError, ValueError, KeyError) as e:
            st.data, st.report, st.error, st.status = None, None, str(e), "Build refused."
            self._changed()
            return
        st.data = result.data
        st.report = gate.run_gate(result.data, gate_inputs(result, st.selection))
        st.error = None
        st.status = "Gate passed." if st.report.passed else "Gate refused the job."
        self._changed()

    def can_send(self, typed_ack: str) -> bool:
        r = self.state.report
        return (self.state.data is not None and r is not None and r.bound_to(self.state.data)
                and r.passed and acknowledged(r, typed_ack))

    def describe(self) -> dict[str, Any]:
        r = self.state.report
        return {"job": str(self.state.job_path) if self.state.job_path else None,
                "passed": None if r is None else r.passed, "flags": None if r is None else r.flags}
