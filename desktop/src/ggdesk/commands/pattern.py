"""ggdesk pattern (stub until its slice lands; see desktop/docs/m1-plan.md section 2.8)."""
from __future__ import annotations

import argparse

from ggdesk.commands._stub import not_implemented


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("args", nargs=argparse.REMAINDER)


def run(args: argparse.Namespace) -> int:
    return not_implemented("pattern")
