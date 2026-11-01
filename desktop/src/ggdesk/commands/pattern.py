"""ggdesk pattern NAME [-p KEY=VALUE]... -o OUT.ggj [--build --recipe R ...] | ggdesk pattern --list

Writes the bench pattern job (desktop/docs/m2-plan.md section 2.3). With --build it then runs
`ggdesk build OUT.ggj -o OUT.m20` (writing OUT.gate.json and OUT.gate.txt) and
`ggdesk preview OUT.m20 -o OUT.svg --job OUT.ggj` with the same selection flags, through those
commands' own code. Exit codes as `ggdesk build`: 0 written (and, with --build, the gate passes),
3 the gate refuses, 1 a build or write error, 2 a usage or parameter error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ggdesk.commands import build as build_cmd
from ggdesk.commands import preview as preview_cmd
from ggdesk.commands._stub import add_selection_arguments
from ggdesk.formats import job as job_format
from ggdesk.patterns import PATTERNS, PatternError, coerce

EXIT_PASS = build_cmd.EXIT_PASS
EXIT_ERROR = build_cmd.EXIT_ERROR
EXIT_USAGE = build_cmd.EXIT_USAGE
EXIT_REFUSED = build_cmd.EXIT_REFUSED


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("name", nargs="?", help="pattern name (see --list)")
    p.add_argument("--list", action="store_true", help="list the patterns, their titles and parameters")
    p.add_argument("-p", "--param", dest="params", action="append", default=[], metavar="KEY=VALUE",
                   help="pattern parameter (repeatable)")
    p.add_argument("-o", "--output", type=Path, help="job file to write (.ggj)")
    p.add_argument("--build", action="store_true",
                   help="also build OUT.m20 with its gate reports and OUT.svg (needs --recipe)")
    add_selection_arguments(p)


def list_text() -> str:
    lines: list[str] = []
    for name in sorted(PATTERNS):
        pat = PATTERNS[name]
        lines.append(f"{name}  ({pat.mode})  {pat.title}")
        for s in pat.params:
            lines.append(f"    -p {s.name}={_default(s.default)}  ({s.type.__name__}) {s.help}")
    return "\n".join(lines) + "\n"


def _default(v: object) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _usage(msg: str) -> int:
    print(f"ggdesk pattern: {msg}", file=sys.stderr)
    return EXIT_USAGE


def run(args: argparse.Namespace) -> int:
    if args.list:
        sys.stdout.write(list_text())
        return EXIT_PASS
    if not args.name:
        return _usage("name a pattern or use --list")
    pat = PATTERNS.get(args.name)
    if pat is None:
        return _usage(f"unknown pattern {args.name!r} (have: {', '.join(sorted(PATTERNS))})")
    if args.output is None:
        return _usage("-o OUT.ggj is required")
    if args.build and not args.recipe:
        return _usage("--build needs --recipe")
    raw: dict[str, str] = {}
    for item in args.params:
        if "=" not in item:
            return _usage(f"-p needs KEY=VALUE, got {item!r}")
        k, v = item.split("=", 1)
        raw[k.strip()] = v.strip()
    try:
        job = pat.generate(**coerce(pat, raw))
    except PatternError as e:
        return _usage(str(e))

    out = Path(args.output)
    try:
        job_format.dump(job, out)
    except OSError as e:
        print(f"ggdesk pattern: cannot write {out}: {e}", file=sys.stderr)
        return EXIT_ERROR
    print(f"wrote {out}")
    if not args.build:
        return EXIT_PASS

    m20 = out.with_suffix(".m20")
    shared = {k: v for k, v in vars(args).items()
              if k in ("recipe", "fixture", "nest", "machine", "overrides", "keep_outs", "library_dirs")}
    rc: int = build_cmd.run(argparse.Namespace(job=out, output=m20, **shared))
    if rc not in (EXIT_PASS, EXIT_REFUSED):
        return rc
    prc: int = preview_cmd.run(argparse.Namespace(file=m20, output=out.with_suffix(".svg"), job=out,
                                                  px_per_mm=5.0, **shared))
    if prc != 0:
        return EXIT_ERROR
    return rc
