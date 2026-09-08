from __future__ import annotations

from pathlib import Path

from common import extract_toten


def test_extract_toten_returns_last_value(tmp_path: Path) -> None:
    outcar = tmp_path / "OUTCAR"
    outcar.write_text(
        " free  energy   TOTEN  =      -10.000000 eV\n free  energy   TOTEN  =      -10.250000 eV\n",
        encoding="ascii",
    )
    assert extract_toten(outcar) == -10.25
    assert extract_toten(tmp_path / "missing") is None
