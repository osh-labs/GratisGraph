from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Tests never read the developer's own user library or write to the real job log.
_TMP = Path(tempfile.mkdtemp(prefix="ggdesk-tests-"))
os.environ["GGDESK_USER_LIBRARY"] = str(_TMP / "user-library")
os.environ.setdefault("GGDESK_LOG_DIR", str(_TMP / "logs"))

DESKTOP = Path(__file__).resolve().parents[1]
REPO = DESKTOP.parent
GOLDEN = REPO / "tests" / "golden"
