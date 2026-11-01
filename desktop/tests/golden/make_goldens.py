"""Desktop goldens: job + library snapshot + selection -> .m20 bytes.

  python tests/golden/make_goldens.py            same as --check
  python tests/golden/make_goldens.py --check    rebuild every case in memory; compare with outputs/ and manifest.json
  python tests/golden/make_goldens.py --write    rewrite outputs/ and manifest.json

Each case is cases/<name>.json: {"job": <path relative to desktop/>, "selection": Selection.to_obj(),
"note": <why the case exists>}. The library snapshot is the seed library (desktop/library/) plus the
test overlay (desktop/tests/fixtures/library/); a user library is never read.

Goldens are the test: --write only in a commit that explains why the output changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DESKTOP = HERE.parents[1]
CASES = HERE / "cases"
OUTPUTS = HERE / "outputs"
MANIFEST = HERE / "manifest.json"

if __name__ == "__main__":   # run as a script from anywhere: make `ggdesk` and the driver importable
    for p in (DESKTOP / "src", DESKTOP.parent):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))

from ggdesk.build import BuildResult, build  # noqa: E402
from ggdesk.formats import job as job_format  # noqa: E402
from ggdesk.library import Library, Selection, load_library  # noqa: E402


def snapshot_library() -> Library:
    return load_library(DESKTOP / "library", None, DESKTOP / "tests" / "fixtures" / "library")


def case_names() -> list[str]:
    return sorted(p.stem for p in CASES.glob("*.json"))


def load_case(name: str) -> tuple[Path, Selection]:
    o = json.loads((CASES / f"{name}.json").read_text(encoding="utf-8"))
    return DESKTOP / o["job"], Selection.from_obj(o["selection"])


def build_case(name: str, lib: Library | None = None) -> BuildResult:
    job_path, sel = load_case(name)
    text = job_path.read_text(encoding="utf-8")
    return build(job_format.loads(text), lib or snapshot_library(), sel, job_text=text)


def manifest_entry(data: bytes) -> dict[str, object]:
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def check() -> list[str]:
    """Problems found (empty when every golden matches)."""
    lib = snapshot_library()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))["cases"]
    problems: list[str] = []
    names = case_names()
    for name in names:
        data = build_case(name, lib).data
        out = OUTPUTS / f"{name}.m20"
        if not out.is_file():
            problems.append(f"{name}: outputs/{name}.m20 missing")
        elif out.read_bytes() != data:
            problems.append(f"{name}: bytes differ from outputs/{name}.m20")
        if manifest.get(name) != manifest_entry(data):
            problems.append(f"{name}: manifest entry {manifest.get(name)} != {manifest_entry(data)}")
    for extra in sorted(set(manifest) - set(names)):
        problems.append(f"{extra}: in manifest.json but has no case file")
    return problems


def write() -> None:
    lib = snapshot_library()
    OUTPUTS.mkdir(exist_ok=True)
    manifest: dict[str, object] = {}
    for name in case_names():
        data = build_case(name, lib).data
        (OUTPUTS / f"{name}.m20").write_bytes(data)
        manifest[name] = manifest_entry(data)
    MANIFEST.write_text(json.dumps({"cases": manifest}, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="compare (default)")
    g.add_argument("--write", action="store_true", help="regenerate outputs and manifest")
    args = ap.parse_args(argv)
    if args.write:
        write()
        print(f"wrote {len(case_names())} golden(s)")
        return 0
    problems = check()
    for p in problems:
        print(p, file=sys.stderr)
    print(f"{len(case_names())} golden(s): {'FAIL' if problems else 'ok'}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
