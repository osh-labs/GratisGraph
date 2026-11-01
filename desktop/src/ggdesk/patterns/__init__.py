"""Bench test patterns (F10). Each pattern makes a gratisgraph-job in the part frame.

Contract (desktop/docs/m2-plan.md section 2.3). Patterns register in PATTERNS by name;
slice M2.3 adds them. Patterns target part `bench-scrap-40` by default (a declared
area on scrap) until the tag blank is measured.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from ggdesk.model.job import Job

DEFAULT_PART = "bench-scrap-40"


@dataclass(frozen=True)
class ParamSpec:
    name: str
    type: type          # int, float, str or bool
    default: Any
    help: str


class Pattern(Protocol):
    name: str
    title: str
    mode: Literal["trace", "fill"]
    params: tuple[ParamSpec, ...]

    def generate(self, **params: Any) -> Job: ...


class PatternError(ValueError):
    """Bad pattern parameters (the message names the parameter)."""


PATTERNS: dict[str, Pattern] = {}


def register(p: Pattern) -> Pattern:
    if p.name in PATTERNS:
        raise ValueError(f"pattern {p.name!r} registered twice")
    PATTERNS[p.name] = p
    return p


def coerce(p: Pattern, raw: Mapping[str, Any]) -> dict[str, Any]:
    """Defaults plus raw values converted to each ParamSpec type; unknown names refused."""
    specs = {s.name: s for s in p.params}
    unknown = sorted(set(raw) - set(specs))
    if unknown:
        raise PatternError(f"{p.name}: unknown parameter(s) {', '.join(unknown)} "
                           f"(have: {', '.join(specs) or 'none'})")
    out = {s.name: s.default for s in p.params}
    for k, v in raw.items():
        t = specs[k].type
        try:
            if t is bool and isinstance(v, str):
                if v.lower() not in ("true", "false"):
                    raise ValueError(v)
                out[k] = v.lower() == "true"
            else:
                out[k] = t(v)
        except (TypeError, ValueError) as e:
            raise PatternError(f"{p.name}: parameter {k} expects {t.__name__}, got {v!r}") from e
    return out


from ggdesk.patterns import builtin as _builtin  # noqa: E402,F401  (registers the built-in patterns)
