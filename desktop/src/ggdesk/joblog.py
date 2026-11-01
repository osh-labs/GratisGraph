"""Job log: one JSON object per line for every send attempt (desktop/docs/m1-plan.md section 2.6).

The gate report carries no timestamp (determinism); start and end times live here.
Default location: <user data dir>/logs/jobs.jsonl (ggdesk.paths naming). GGDESK_LOG_DIR
overrides the directory (tests, portable installs). Records never hold secrets: the
acknowledgement is logged as a boolean, never as the typed text.
"""
from __future__ import annotations

import json
import os
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ggdesk import paths

LOG_NAME = "jobs.jsonl"


def default_path() -> Path:
    env = os.environ.get("GGDESK_LOG_DIR")
    base = Path(env) if env else paths.user_data_dir() / "logs"
    return base / LOG_NAME


class JobLog:
    """Append-only JSON-lines log. Thread-safe within one process."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_path()
        self._lock = threading.Lock()

    def append(self, record: Mapping[str, Any]) -> None:
        line = json.dumps(dict(record), sort_keys=True, ensure_ascii=False, separators=(", ", ": "))
        if "\n" in line or "\r" in line:   # json.dumps escapes these; a raw one would split a record
            raise ValueError("job log record would span lines")
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8", newline="\n") as f:
                f.write(line + "\n")

    def records(self) -> list[dict[str, Any]]:
        """Every record, oldest first (empty when the log does not exist yet)."""
        if not self.path.exists():
            return []
        out: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
        return out
