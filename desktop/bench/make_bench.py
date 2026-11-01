#!/usr/bin/env python3
"""Generate (or check) the bench package: jobs, .m20 bytes, gate reports, previews, manifest.

    python desktop/bench/make_bench.py            check: rebuild in memory, compare with the committed files
    python desktop/bench/make_bench.py --write    regenerate every file (explain why in the commit)

Each entry is built by the same `ggdesk build` / `ggdesk preview` commands an operator would type, from
the repository root, with the seed library only (no user library). MANIFEST.md lists every command
and every sha256. Files built against `bare-bed` and `bench-scrap-40` say so: the tag blank and its
nest are not measured yet (G1, G2).
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
DESKTOP = HERE.parent
REPO = DESKTOP.parent


@dataclass(frozen=True)
class Entry:
    stage: str            # V1, V2, ...
    name: str             # output stem
    job: str              # job file under desktop/bench/<stage>/ (committed)
    args: tuple[str, ...]  # selection flags for ggdesk build
    note: str = ""
    pattern: tuple[str, ...] = ()   # `ggdesk pattern` arguments that (re)generate the job file first
    commit: bool = True             # False: too large to commit; MANIFEST.md carries its sha256 and command


TRACE = ("--recipe", "scrap-rotary-diamond-trace", "--fixture", "bare-bed")
# Fill builds before V3 has measured the tip width (G3) and stepover (G6): PLACEHOLDER values, printed in
# every gate report as bench overrides. The V3 sheet says to regenerate with the measured values.
FILL_PLACEHOLDER = ("--recipe", "scrap-rotary-diamond-fill", "--fixture", "bare-bed",
                    "--set", "tip_width_mm=0.2", "--set", "stepover_mm=0.1")

ENTRIES: tuple[Entry, ...] = (
    Entry("V1", "v1-asymmetric", "v1-asymmetric.ggj", TRACE,
          "Asymmetric orientation and position test on scrap (bare-bed, bench-scrap-40)."),
    *(Entry("V2", f"v2-pz{pz}", "v2-square-10mm.ggj", (*TRACE, "--set", f"pz={pz}"),
            f"PZ sweep: 10 mm square at PZ {pz} (bench override on the draft run-3 recipe).")
      for pz in (20, 50, 80, 100)),
    Entry("V2", "v2-stop", "v2-stop-long.ggj", TRACE,
          "Stop behaviour: a longer job (about 2 min) to stop mid-run with the panel stop and with !1B 0;."),
    Entry("V3", "v3-char-ladder-trace", "v3-char-ladder-trace.ggj", TRACE,
          "Part A: character-height ladder, single-line (G5 trace).", ("char-ladder-trace",)),
    Entry("V3", "v3-line-width", "v3-line-width.ggj", TRACE,
          "Part B: 10 mm square; measure the groove width (G3 tip width).", ("pz-square",)),
    Entry("V3", "v3-stepover-ladder", "v3-stepover-ladder.ggj", TRACE,
          "Part C: stepover ladder, explicit hatch lines 0.05 to 0.30 mm (G6).", ("stepover-ladder",)),
    Entry("V3", "v3-char-ladder-fill", "v3-char-ladder-fill.ggj", FILL_PLACEHOLDER,
          "Part D: character-height ladder, filled (G5 fill). PLACEHOLDER tip width 0.2 mm and stepover 0.1 mm: "
          "regenerate with the V3 part B and C values before cutting.", ("char-ladder-fill",)),
    *(Entry("V3", f"v3-job-size-{kb}kb", f"v3-job-size-{kb}kb.ggj", TRACE,
            f"Part E: job-size ladder, {kb} KB (G9). Run tool-reversed."
            + ("" if kb <= 64 else " Not committed (size): regenerate with the command; check the sha256."),
            ("job-size-ladder", "-p", f"target_kb={kb}"), commit=kb <= 64)
      for kb in (16, 64, 256, 512, 1024)),
    Entry("V3", "v3-corner-test", "v3-corner-test.ggj", TRACE,
          "Part F: corner test at segment accel 551 (G7).", ("corner-test",)),
    Entry("V4", "v4-datum-crosshair", "v4-datum-crosshair.ggj", TRACE,
          "Part A rehearsal on scrap: datum crosshair (G2 once on the nest).", ("datum-crosshair",)),
    Entry("V4", "v4-first-article-trace", "v4-first-article-trace.ggj", TRACE,
          "Part B rehearsal on scrap: generic two-line tag layout, single-line text (placeholder text)."),
    Entry("V4", "v4-first-article-fill", "v4-first-article-fill.ggj", FILL_PLACEHOLDER,
          "Part B rehearsal on scrap: the same layout, filled. PLACEHOLDER tip width and stepover."),
    Entry("V4", "v4-repeat-batch", "v4-repeat-batch.ggj", TRACE,
          "Part C rehearsal on scrap: repeatability layout, quantity 10 (G11).", ("repeat-batch",)),
)


def _pattern_cmd(e: Entry) -> list[str]:
    if not e.pattern:
        return []
    name, *params = e.pattern
    return ["pattern", name, *params, "-o", f"desktop/bench/{e.stage}/{e.job}"]


def _cmd(e: Entry) -> tuple[list[str], list[str]]:
    stage = f"desktop/bench/{e.stage}"
    build = ["build", f"{stage}/{e.job}", "-o", f"{stage}/{e.name}.m20", *e.args]
    preview = ["preview", f"{stage}/{e.name}.m20", "-o", f"{stage}/{e.name}.svg", "--job", f"{stage}/{e.job}",
               *e.args]
    return build, preview


def _run(argv: list[str]) -> int:
    from ggdesk.cli import main

    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        rc = main(argv)
    if rc not in (0, 3):
        sys.stderr.write(out.getvalue())
    return rc


def generate(root: Path) -> dict[str, str]:
    """Build every entry under root (a copy of the repository layout). Returns {relative path: text summary}."""
    os.environ["GGDESK_USER_LIBRARY"] = str(root / "no-user-library")
    cwd = Path.cwd()
    os.chdir(root)
    try:
        rows: dict[str, str] = {}
        for e in ENTRIES:
            build, preview = _cmd(e)
            pat = _pattern_cmd(e)
            (root / "desktop" / "bench" / e.stage).mkdir(parents=True, exist_ok=True)
            if pat and _run(pat) != 0:
                raise SystemExit(f"{e.name}: ggdesk pattern failed")
            rc = _run(build)
            if rc != 0:
                raise SystemExit(f"{e.name}: ggdesk build exited {rc} (the gate refused or the build failed)")
            if e.commit and _run(preview) != 0:
                raise SystemExit(f"{e.name}: ggdesk preview failed")
            cmds = ([" ".join(["ggdesk", *pat])] if pat else []) + [" ".join(["ggdesk", *build])]
            rows[e.name] = " && ".join(cmds)
        return rows
    finally:
        os.chdir(cwd)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def manifest(root: Path, rows: dict[str, str]) -> str:
    from ggdesk.gate import GateReport

    lines = ["# Bench package manifest", "",
             "Generated by `python desktop/bench/make_bench.py --write`; checked in CI by "
             "`desktop/tests/unit/test_bench_package.py`. Regenerate a file with the command shown, from the "
             "repository root. Every `.m20` here was built against the seed library only.", "",
             "| Stage | File | Bytes | sha256 | Gate | Flags (ack phrase) | Command |",
             "|---|---|---|---|---|---|---|"]
    for e in ENTRIES:
        m20 = root / "desktop" / "bench" / e.stage / f"{e.name}.m20"
        rep = GateReport.from_json(m20.with_suffix(".gate.json").read_text(encoding="utf-8"))
        flags = f"{rep.flags} (`{rep.ack_phrase}`)" if rep.flags else "0"
        lines.append(f"| {e.stage} | `{e.name}.m20` | {m20.stat().st_size} | `{_sha(m20)}` | "
                     f"{'PASS' if rep.passed else 'REFUSED'} | {flags} | `{rows[e.name]}` |")
    lines += ["", "Notes:", ""]
    lines += [f"- `{e.name}`: {e.note}" for e in ENTRIES]
    lines += ["", "Rows marked \"Not committed\" are too large for the repository: run the command from the "
              "repository root and check that the file's sha256 equals the manifest before sending.",
              "", "All files target fixture `bare-bed` (datum = machine home, part origin at machine (50, 50) mm) "
              "and part `bench-scrap-40` (a declared 40 x 40 mm area), because the tag blank (G1) and its nest "
              "(G2) are not measured. The vise jaws are not modelled: run each job tool-reversed first and watch "
              "that the head stays clear of the jaws.", ""]
    return "\n".join(lines)


def _outputs(root: Path) -> list[Path]:
    out: list[Path] = []
    for e in ENTRIES:
        d = root / "desktop" / "bench" / e.stage
        if e.commit:
            out += [d / f"{e.name}{s}" for s in (".m20", ".gate.json", ".gate.txt", ".svg")]
            if e.pattern:
                out.append(d / e.job)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "desktop").mkdir()
        generated = {e.job for e in ENTRIES if e.pattern}
        shutil.copytree(HERE, root / "desktop" / "bench",
                        ignore=lambda d, names: [n for n in names if n in generated or n == "MANIFEST.md"
                                                 or n == "__pycache__" or n.endswith((".m20", ".svg"))
                                                 or ".gate." in n])
        rows = generate(root)
        text = manifest(root, rows)
        (root / "desktop" / "bench" / "MANIFEST.md").write_text(text, encoding="utf-8", newline="\n")
        files = _outputs(root) + [root / "desktop" / "bench" / "MANIFEST.md"]
        bad: list[str] = []
        for f in files:
            rel = f.relative_to(root)
            target = REPO / rel
            if args.write:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(f.read_bytes())
            elif not target.exists() or target.read_bytes() != f.read_bytes():
                bad.append(str(rel))
    if bad:
        print("bench package out of date (run make_bench.py --write and explain why in the commit):")
        print("\n".join(f"  {b}" for b in bad))
        return 1
    print("bench package " + ("written" if args.write else "up to date"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
