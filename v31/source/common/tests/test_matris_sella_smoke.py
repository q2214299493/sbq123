from pathlib import Path

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.emt import EMT

from scripts.artifact_io import sha256_file, write_json_atomic
from scripts.matris_sella_smoke import BudgetCalculator, validate_request


def test_force_evaluation_budget_is_enforced():
    atoms = Atoms('Cu', positions=[[0, 0, 0]])
    calculator = BudgetCalculator(EMT(), 1, 10)
    atoms.calc = calculator
    assert np.isfinite(atoms.get_forces()).all()
    atoms.positions[0, 0] += 0.01
    with pytest.raises(RuntimeError, match='budget exhausted'):
        atoms.get_forces()
    assert calculator.evaluations == 1


@pytest.mark.parametrize('field,value', [('max_steps', 4), ('maximum_evaluations', 81),
                                        ('maximum_wall_seconds', 301), ('execution_authorized', False),
                                        ('training_authorized', True), ('minimum_pair_distance_A', float('nan'))])
def test_smoke_authorization_and_bounds(tmp_path: Path, field, value):
    sample = tmp_path / 'sample'
    sample.write_bytes(b'test fixture')
    ref = {'path': str(sample), 'sha256': sha256_file(sample)}
    request = {'document_kind': 'matris_sella_smoke_request', 'execution_authorized': True,
               'training_authorized': False, 'vasp_authorized': False, 'scientific_acceptance_authorized': False,
               'settings': {'max_steps': 3, 'fmax_eV_per_A': 0.05, 'delta0_A': 0.02},
               'maximum_evaluations': 80, 'maximum_wall_seconds': 300,
               'minimum_pair_distance_A': 0.65, 'maximum_displacement_A': 0.15,
               'structure': ref, 'checkpoint': ref}
    path = tmp_path / 'request.json'
    write_json_atomic(path, request)
    assert validate_request(path)['execution_authorized']
    if field == 'max_steps':
        request['settings'][field] = value
    else:
        request[field] = value
    write_json_atomic(path, request)
    with pytest.raises(ValueError):
        validate_request(path)
