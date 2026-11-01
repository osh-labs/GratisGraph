from __future__ import annotations

import json
from pathlib import Path

import fastjsonschema
import pytest

from ggdesk.formats import job as jf
from ggdesk.model.job import FillOp, TraceOp
from tests.conftest import DESKTOP

EXAMPLES = sorted((DESKTOP / "docs" / "examples").glob("*.ggj"))
SCHEMA = fastjsonschema.compile(json.loads(jf.SCHEMA_PATH.read_text(encoding="utf-8")))


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_examples_round_trip_and_match_schema(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    SCHEMA(json.loads(text))
    job = jf.loads(text)
    assert jf.dumps(job) == text


def test_examples_exist() -> None:
    assert len(EXAMPLES) >= 3


def test_unknown_keys_preserved() -> None:
    job = jf.load(DESKTOP / "docs" / "examples" / "fill-square-hole.ggj")
    assert job.extra == {"producer_note": {"kept": "unknown keys are preserved"}}
    assert isinstance(job.operations[0], FillOp)


def _doc(**kw: object) -> dict[str, object]:
    d: dict[str, object] = {"format": "gratisgraph-job", "version": 1, "units": "mm", "part": "p",
                            "operations": [{"op": "trace", "paths": [{"points": [[0, 0], [1, 0]]}]}]}
    d.update(kw)
    return d


def test_minimal() -> None:
    job = jf.from_obj(_doc())
    op = job.operations[0]
    assert isinstance(op, TraceOp) and op.mode_hint == "trace"
    assert job.quantity == 1 and job.chord_tolerance_mm == 0.01


@pytest.mark.parametrize(("change", "where"), [
    ({"format": "x"}, "$.format"),
    ({"version": 2}, "$.version"),
    ({"version": True}, "$.version"),
    ({"units": "in"}, "$.units"),
    ({"part": ""}, "$.part"),
    ({"quantity": 0}, "$.quantity"),
    ({"chord_tolerance_mm": 0.02}, "$.chord_tolerance_mm"),
    ({"chord_tolerance_mm": 0}, "$.chord_tolerance_mm"),
    ({"operations": []}, "$.operations"),
    ({"operations": [{"op": "drill"}]}, "$.operations[0].op"),
    ({"operations": [{"op": "trace", "paths": [{"points": [[0, 0]]}]}]}, "$.operations[0].paths[0].points"),
    ({"operations": [{"op": "trace", "paths": [{"points": [[0, 0], [1, 0], [0, 0]], "closed": True}]}]},
     "$.operations[0].paths[0].points"),
    ({"operations": [{"op": "trace", "paths": [{"points": [[0, "a"], [1, 0]]}]}]},
     "$.operations[0].paths[0].points[0][1]"),
    ({"operations": [{"op": "trace", "paths": [{"points": [[0, 0], [1, 0]], "speed": 3}]}]},
     "$.operations[0].paths[0]"),
    ({"operations": [{"op": "fill", "regions": [{"outer": [[0, 0], [1, 0]]}]}]},
     "$.operations[0].regions[0].outer"),
    ({"operations": [{"op": "trace", "char_height_mm": -1, "paths": [{"points": [[0, 0], [1, 0]]}]}]},
     "$.operations[0].char_height_mm"),
])
def test_rejects_with_path(change: dict[str, object], where: str) -> None:
    with pytest.raises(jf.JobFormatError) as e:
        jf.from_obj(_doc(**change))
    assert str(e.value).startswith(where + ":")


def test_rejects_non_json() -> None:
    with pytest.raises(jf.JobFormatError):
        jf.loads("{not json")


def test_dump_is_deterministic(tmp_path: Path) -> None:
    job = jf.from_obj(_doc(reference="r", extra_key=[1, 2]))
    p = tmp_path / "a.ggj"
    jf.dump(job, p)
    assert p.read_bytes() == jf.dumps(job).encode("utf-8")
    assert b"\r\n" not in p.read_bytes()
    assert list(json.loads(p.read_text())) [-1] == "extra_key"
