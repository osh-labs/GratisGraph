"""Output gate types (build plan section 9). Rules live in gate/rules_*.py (M1.2)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from ggdesk import gts_read
from ggdesk.library.model import EntryRef
from ggdesk.library.select import Resolved, Selection
from ggdesk.model.toolpath import Intent


class Severity(StrEnum):
    HARD = "hard"
    SOFT = "soft"


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: Severity
    message: str
    offset: int | None = None


@dataclass(frozen=True)
class GateConfig:
    max_run_time_s: float = 1800.0   # S5: a project setting, not a machine fact


@dataclass(frozen=True)
class GateInputs:
    resolved: Resolved
    intent: Intent | None
    job_sha256: str | None
    selection: Selection
    config: GateConfig = field(default_factory=GateConfig)
    target_model_code: int | None = None   # the connected machine's !ID model code, at send time


class Rule(Protocol):
    id: str
    severity: Severity
    title: str

    def check(self, data: bytes, job: gts_read.Job, inputs: GateInputs) -> list[Finding]: ...


def ack_phrase(n: int) -> str:
    """What the operator types to accept n soft flags."""
    if n <= 0:
        return ""
    return f"I ACCEPT {n} FLAG" if n == 1 else f"I ACCEPT {n} FLAGS"


@dataclass(frozen=True)
class GateReport:
    sha256: str
    size: int
    app_version: str
    model_code: int | None
    entries: tuple[EntryRef, ...]
    selection: Selection
    job_sha256: str | None
    findings: tuple[Finding, ...]
    residual: tuple[str, ...]
    estimate_s: float | None
    rules_run: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not any(f.severity is Severity.HARD for f in self.findings)

    @property
    def flags(self) -> int:
        return sum(1 for f in self.findings if f.severity is Severity.SOFT)

    @property
    def ack_phrase(self) -> str:
        return ack_phrase(self.flags)

    def bound_to(self, data: bytes) -> bool:
        return len(data) == self.size and hashlib.sha256(data).hexdigest() == self.sha256

    def to_obj(self) -> dict[str, Any]:
        return {
            "format": "gratisgraph-gate-report", "version": 1,
            "sha256": self.sha256, "size": self.size, "app_version": self.app_version,
            "model_code": self.model_code,
            "entries": [{"kind": e.kind, "id": e.id, "version": e.version, "sha256": e.sha256}
                        for e in self.entries],
            "selection": self.selection.to_obj(), "job_sha256": self.job_sha256,
            "passed": self.passed, "flags": self.flags,
            "findings": [{"rule": f.rule, "severity": str(f.severity), "message": f.message, "offset": f.offset}
                         for f in self.findings],
            "residual": list(self.residual), "estimate_s": self.estimate_s, "rules_run": list(self.rules_run),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_obj(), indent=2, sort_keys=True) + "\n"

    @staticmethod
    def from_json(text: str) -> GateReport:
        o = json.loads(text)
        if o.get("format") != "gratisgraph-gate-report" or o.get("version") != 1:
            raise ValueError("not a gratisgraph gate report v1")
        return GateReport(
            o["sha256"], o["size"], o["app_version"], o["model_code"],
            tuple(EntryRef(e["kind"], e["id"], e["version"], e["sha256"]) for e in o["entries"]),
            Selection.from_obj(o["selection"]), o["job_sha256"],
            tuple(Finding(f["rule"], Severity(f["severity"]), f["message"], f["offset"]) for f in o["findings"]),
            tuple(o["residual"]), o["estimate_s"], tuple(o["rules_run"]))

    def to_text(self) -> str:
        lines = [f"Gate report  {'PASS' if self.passed else 'REFUSED'}"
                 + (f", {self.flags} flag(s) to acknowledge" if self.passed and self.flags else ""),
                 f"sha256       {self.sha256}",
                 f"bytes        {self.size}",
                 f"model code   {'none' if self.model_code is None else f'0x{self.model_code:04X}'}",
                 f"app          ggdesk {self.app_version}",
                 "library      " + ", ".join(f"{e.kind}:{e.id} v{e.version}" for e in self.entries)]
        if self.estimate_s is not None:
            lines.append(f"run time     about {self.estimate_s:.0f} s (estimate)")
        hard = [f for f in self.findings if f.severity is Severity.HARD]
        soft = [f for f in self.findings if f.severity is Severity.SOFT]
        lines.append("")
        lines.append(f"Hard (block): {len(hard)}")
        lines += [f"  {f.rule}  {f.message}" + (f"  @{f.offset}" if f.offset is not None else "") for f in hard]
        lines.append(f"Soft (flag):  {len(soft)}")
        lines += [f"  {f.rule}  {f.message}" for f in soft]
        if self.passed and soft:
            lines.append(f"To send, type: {self.ack_phrase}")
        lines.append("")
        lines.append("Residual status (always shown):")
        lines += [f"  {r}" for r in self.residual]
        return "\n".join(lines) + "\n"


def acknowledged(report: GateReport, typed: str) -> bool:
    """True when no flags, or the operator typed the exact phrase repeating the count."""
    if report.flags == 0:
        return True
    return typed.strip() == report.ack_phrase
