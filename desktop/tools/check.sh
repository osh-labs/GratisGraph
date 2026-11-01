#!/usr/bin/env bash
# Fast pre-push check for desktop/: lint, types, and the core tests.
#
#   desktop/tools/check.sh            ruff, mypy, core tests
#   desktop/tools/check.sh --no-tests ruff and mypy only
#   desktop/tools/check.sh --all      also the GUI tests (needs PySide6 + pytest-qt)
#
# CI (.github/workflows/desktop.yml) runs Windows and the GUI suite; reproduce
# a single failing CI test locally rather than re-running a whole job.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/desktop"

mode=core
case "${1:-}" in
  "") ;;
  --no-tests) mode=none ;;
  --all) mode=all ;;
  *) echo "usage: desktop/tools/check.sh [--no-tests | --all]" >&2; exit 2 ;;
esac

echo "== ruff"
python -m ruff check src tests

echo "== mypy"
if python -c "import PySide6" 2>/dev/null; then
  python -m mypy
else
  python -m mypy src/ggdesk
fi

case "$mode" in
  none) exit 0 ;;
  core) echo "== core tests"; exec python -m pytest -q tests/unit ;;
  all)  echo "== all tests"; QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}" exec python -m pytest -q ;;
esac
