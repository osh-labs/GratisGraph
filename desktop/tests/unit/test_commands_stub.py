from __future__ import annotations

import pytest

from ggdesk.cli import main


def test_library_validate(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["library", "validate"]) == 0
    assert "0 error(s)" in capsys.readouterr().out


def test_help_lists_every_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    for name in ("check", "build", "preview", "send", "pattern", "library", "inspect", "version"):
        assert name in out
