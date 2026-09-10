"""Persist the completed work-side geometry review; no execution authority."""
from datetime import datetime, timezone

import numpy as np
from ase.geometry import find_mic
from ase.io import read

from archive.int06_mid_path_20260910.review_path import BASE, PATH
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.ts_strategy_engine.path_evidence import validate_path_review


def main() -> None:
    movie = read(PATH/'movie.xyz', index=':', format='xyz')
    assert len(movie) == 5
    for i, frame in enumerate(movie):
        original = read(PATH/f'{i:02d}/POSCAR')
        assert frame.get_chemical_symbols() == original.get_chemical_symbols()
        _, displacement = find_mic(frame.positions-original.positions, original.cell, pbc=(True, True, False))
        assert max(displacement) < 2e-5
    review = load_json_object(PATH/'path_review.draft.json')
    review.update(status='accepted', reviewer='Codex work-side geometry review',
                  reviewed_at=datetime.now(timezone.utc).isoformat(),
                  notes='Top/side path_review.png inspected. H50 follows a continuous surface trajectory; '
                        'five VTST XYZ frames match POSCARs. Exact MIC checks preserve C2HO connectivity, '
                        'bottom18 fixed atoms and atom order. No collision or periodic jump; arriving '
                        'Fe39 contact decreases while leaving Fe40 increases. Local initial path only: '
                        'no VASP path energies/forces, no TS acceptance and no submission approval.',
                  visual_review_file=str(BASE/'path_review.png'),
                  visual_review_sha256=sha256_file(BASE/'path_review.png'),
                  geometry_evidence_sha256=sha256_file(PATH/'exact_mic_geometry.json'))
    write_json_exclusive(PATH/'path_review.json', review)
    assert validate_path_review(PATH/'path_review.json', PATH/'path_generation_report.json')[0]
    assert np.isfinite(load_json_object(PATH/'exact_mic_geometry.json')['rows'][0]['minimum_distance_A'])
    print('accepted initial geometry; five movie frames verified; no execution authorization')


if __name__ == '__main__':
    main()
