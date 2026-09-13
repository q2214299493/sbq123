"""Reproduce same-geometry magnetic/force comparison; never run VASP."""
import csv
import json
from pathlib import Path

import numpy as np
from pymatgen.io.vasp.inputs import Incar, Poscar
from pymatgen.io.vasp.outputs import Outcar
from pymatgen.util.coord import pbc_shortest_vectors

from scripts.artifact_io import sha256_file, write_json

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'calculations/fe110_c2ho_h_to_c2h2o_ts_20260822'
OLD = BASE / 'h_migration_int06_mid_scf_normal_20260912'
NEW = BASE / 'h_migration_int06_mid_scf_near_linear_20260913'
REVIEW = ROOT / 'docs/reviews/scf_magnetic_recovery_20260913'


def parse(path):
    assert path.stat().st_size < 2_000_000
    raw = path.read_bytes()
    assert b'\x00' not in raw
    text = raw.decode()
    assert 'aborting loop because EDIFF is reached' in text
    assert 'General timing and accounting' in text
    moments = np.array([x['tot'] for x in Outcar(path).magnetization])
    rows = []
    for line in text.rsplit('TOTAL-FORCE (eV/Angst)', 1)[1].splitlines():
        values = line.split()
        if len(values) == 6:
            try:
                rows.append([float(x) for x in values])
            except ValueError:
                pass
        if len(rows) == 50:
            break
    forces = np.array(rows)[:, 3:]
    assert moments.shape == (50,) and forces.shape == (50, 3)
    assert np.isfinite(moments).all() and np.isfinite(forces).all()
    return moments, forces


def main():
    out0 = OLD / 'completed_20260912/OUTCAR'
    out1 = NEW / 'completed_review_20260913/OUTCAR'
    m0, f0 = parse(out0)
    m1, f1 = parse(out1)
    a = Poscar.from_file(OLD / 'POSCAR')
    b = Poscar.from_file(NEW / 'POSCAR')
    c = Poscar.from_file(NEW / 'completed_review_20260913/CONTCAR')
    for other in (b, c):
        assert a.structure.species == other.structure.species
        assert np.allclose(a.structure.lattice.matrix, other.structure.lattice.matrix,
                           atol=1e-10, rtol=0)
        assert np.array_equal(a.selective_dynamics, other.selective_dynamics)
        vectors = pbc_shortest_vectors(a.structure.lattice, a.structure.frac_coords,
                                      other.structure.frac_coords)
        assert max(np.linalg.norm(vectors[i, i]) for i in range(50)) < 1e-10
    before = Incar.from_file(NEW / 'INCAR')
    after = Incar.from_file(REVIEW / 'INCAR.recommended')
    delta = [k for k in sorted(set(before) | set(after)) if before.get(k) != after.get(k)]
    assert delta == ['MAGMOM'], delta
    assert np.array_equal(after['MAGMOM'], m0)
    negative = np.where(m1[:45] < 0)[0].tolist()
    assert all(not any(a.selective_dynamics[i]) for i in negative)
    rows = []
    for i, site in enumerate(a.structure):
        rows.append({'index_zero': i, 'atom_one': i + 1, 'species': site.specie.symbol,
                     'z_A': float(site.z), 'fixed': not any(a.selective_dynamics[i]),
                     'm_9752745_muB': m0[i], 'm_9754301_muB': m1[i],
                     'delta_m_muB': m1[i] - m0[i],
                     'force_old_eVA': float(np.linalg.norm(f0[i])),
                     'force_new_eVA': float(np.linalg.norm(f1[i])),
                     'force_difference_eVA': float(np.linalg.norm(f1[i] - f0[i]))})
    csv_path = REVIEW / 'per_atom_comparison.csv'
    with csv_path.open('x', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    report = {'negative_Fe_zero_indices': negative, 'all_negative_Fe_fixed': True,
              'same_geometry_PBC': True, 'only_candidate_change': delta,
              'component_force_rmse_eVA': float(np.sqrt(np.mean((f1 - f0)**2))),
              'maximum_force_difference_eVA': float(np.linalg.norm(f1-f0, axis=1).max()),
              'movable_maximum_force_difference_eVA': max(
                  row['force_difference_eVA'] for row in rows if not row['fixed']),
              'source_bindings': [{'path': str(p), 'sha256': sha256_file(p)} for p in
                                  (out0, out1, OLD/'POSCAR', NEW/'POSCAR',
                                   NEW/'INCAR', REVIEW/'INCAR.recommended', csv_path)],
              'status': 'REVIEW_ONLY_NOT_AUTHORIZED_FOR_SUBMISSION'}
    write_json(REVIEW / 'comparison.json', report)
    print(json.dumps({k: v for k, v in report.items() if k != 'source_bindings'}))


if __name__ == '__main__':
    main()
