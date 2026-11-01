"""measurements-needed.md lists every needs_measurement fact in the seed library."""
from __future__ import annotations

from ggdesk.library import load_library, unmeasured
from tests.conftest import DESKTOP

DOC = DESKTOP / "docs" / "validation" / "measurements-needed.md"


def test_every_unmeasured_fact_is_listed() -> None:
    text = DOC.read_text(encoding="utf-8")
    rows = {(line.split("|")[1].strip(), line.split("|")[2].strip(), line.split("|")[3].strip())
            for line in text.splitlines() if line.startswith("| `")}
    missing = []
    for kind, eid, field, fact in unmeasured(load_library(DESKTOP / "library")):
        key = (f"`{kind}s/{eid}`", f"`{field}`", fact.gap or "")
        if key not in rows:
            missing.append(key)
    assert missing == []


def test_count_in_bottom_line() -> None:
    n = len(unmeasured(load_library(DESKTOP / "library")))
    assert f"{n} library facts are `needs_measurement`" in DOC.read_text(encoding="utf-8")
