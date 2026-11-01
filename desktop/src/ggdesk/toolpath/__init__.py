"""Toolpath stages for the build (desktop/docs/m1-plan.md section 2.5).

trace (part frame, mm) -> to_machine_units (machine frame, device units, quantised once)
-> order (pen-up travel; reorders and reverses only).
"""
from ggdesk.toolpath.order import order
from ggdesk.toolpath.trace import trace
from ggdesk.toolpath.transform import to_machine_units, to_machine_units_counted

__all__ = ["order", "to_machine_units", "to_machine_units_counted", "trace"]
