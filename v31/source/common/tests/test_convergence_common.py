from __future__ import annotations

from pathlib import Path

import pytest

from common import extract_toten
from scripts.convergence.setup_true_fe110_thickness_retest import last_toten


def test_extract_toten_returns_last_value(tmp_path: Path) -> None:
    outcar = tmp_path / "OUTCAR"
    outcar.write_text(
        " free  energy   TOTEN  =      -10.000000 eV\n free  energy   TOTEN  =      -10.250000 eV\n",
        encoding="ascii",
    )
    assert extract_toten(outcar) == -10.25
    assert extract_toten(tmp_path / "missing") is None


@pytest.mark.parametrize('line,value', [
    (' free  energy   TOTEN  =       -10.50000000 eV', -10.5),
    ('free\tenergy TOTEN = +1.25E+2 eV', 125.0),
    ('free energy TOTEN = -2.4e-3 eV', -0.0024),
    ('no energy record', None),
])
def test_shared_toten_full_tokens(tmp_path, line, value):
    path = tmp_path/'OUTCAR'
    path.write_text(line+'\n')
    assert extract_toten(path) == last_toten(path) == value
    assert last_toten(tmp_path/'missing') is None


@pytest.mark.parametrize('token', ['NaN', 'Inf', '-Inf', '1E', '1.2oops', '--2', '', '1.0 junk', '1_0', '1e999'])
def test_last_invalid_toten_does_not_fall_back(tmp_path, token):
    path = tmp_path/'OUTCAR'
    path.write_text('free energy TOTEN = -10.0 eV\n'+f'free energy TOTEN = {token} eV\n')
    for reader in [extract_toten, last_toten]:
        with pytest.raises(ValueError):
            reader(path)
