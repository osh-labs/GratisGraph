"""Turn CLI selection flags into a Selection and a Library (shared by build, check, preview, send)."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ggdesk import paths
from ggdesk.library import Library, Selection, load_library
from ggdesk.model.geometry import Pt


class UsageError(ValueError):
    pass


def parse_value(text: str) -> Any:
    t = text.strip()
    if t.lower() in ("true", "false"):
        return t.lower() == "true"
    try:
        return int(t)
    except ValueError:
        pass
    try:
        return float(t)
    except ValueError as e:
        raise UsageError(f"cannot read value {text!r}") from e


def parse_overrides(items: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for it in items:
        if "=" not in it:
            raise UsageError(f"--set needs KEY=VALUE, got {it!r}")
        k, v = it.split("=", 1)
        out[k.strip()] = parse_value(v)
    return out


def parse_keep_out(text: str) -> tuple[Pt, ...]:
    try:
        x0, y0, x1, y1 = (float(v) for v in text.split(","))
    except ValueError as e:
        raise UsageError(f"--keep-out needs X0,Y0,X1,Y1 in mm, got {text!r}") from e
    xa, xb, ya, yb = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)
    return ((xa, ya), (xb, ya), (xb, yb), (xa, yb))


def selection_from_args(args: argparse.Namespace) -> Selection:
    if not args.recipe:
        raise UsageError("--recipe is required")
    return Selection(args.machine, args.recipe, args.fixture, args.nest, parse_overrides(args.overrides),
                     tuple(parse_keep_out(k) for k in args.keep_outs))


def library_from_args(args: argparse.Namespace) -> Library:
    """Seed, then the user library, then --library directories: the same order `ggdesk send` uses."""
    return load_library(None, paths.user_library(), *(Path(d) for d in getattr(args, "library_dirs", [])))
