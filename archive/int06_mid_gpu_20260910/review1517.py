"""Independent, no-model scientific review of the returned GPU1517 path."""
import os
import shutil
import subprocess

import matplotlib
import numpy as np
from ase.geometry import find_mic
from ase.io import read

from archive.int06_mid_gpu_20260910.gpu0_attempt import attempt
from archive.int06_mid_gpu_20260910.inspect_remote import BASE, ROOT
from scripts.adsmind_lite.relaxed_analysis import connectivity_edges
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.dual_model_ml_neb import _load_request
from scripts.ml_candidate_source import load_candidate_path
from scripts.neb_agent.diagnose_path_geometry import diagnose
from scripts.neb_agent.analyze_neb_outputs import analyze

matplotlib.use('Agg')
import matplotlib.pyplot as plt

REVIEW = attempt.ATTEMPT / 'review_job1517'
RAW = REVIEW / 'raw'
OUTPUT = RAW / 'output/production'
MANIFEST = OUTPUT / 'dual_model_gpu_ml_neb_path_manifest.candidate.json'
EXPORT = REVIEW / 'path_review_export'


def main():
    request = _load_request(RAW / 'request.json')
    manifest = load_json_object(MANIFEST)
    for name in request['images']:
        source = BASE / 'payload' / name['path']
        destination = RAW / name['path']
        destination.parent.mkdir(parents=True, exist_ok=True)
        assert not destination.exists()
        shutil.copyfile(source, destination)
    for ref in [manifest['source_request'], manifest['producer_exit_record']]:
        assert sha256_file(OUTPUT / ref['path']) == ref['sha256']
    assert manifest['models'] == request['models'] and manifest['reaction'] == request['reaction']
    assert manifest['runner_sha256'] == request['runtime_bindings']['dual_model_ml_neb.py']
    assert load_json_object(OUTPUT / 'producer_exit_record.json')['exit_code'] == 0
    atoms, _ = load_candidate_path(request, manifest, MANIFEST, RAW / 'request.json', method='ml_neb')
    EXPORT.mkdir(exist_ok=False)
    rows = []
    for i, a in enumerate(atoms):
        a.pbc = (True, True, False)
        d = a.get_all_distances(mic=True)
        _, steps = find_mic(a.positions - atoms[max(0, i-1)].positions, a.cell, pbc=a.pbc)
        _, fixed = find_mic(a.positions[:18] - atoms[0].positions[:18], a.cell, pbc=a.pbc)
        edges = connectivity_edges(a, list(range(45, 50)), 1.25, 0.35)
        assert edges == [(0, 1), (0, 3), (1, 2)]
        assert max(fixed) < 1e-8
        rows.append({'image': f'{i:02d}', 'sha256': sha256_file(OUTPUT / manifest['images'][i]['structure_path']),
                     'minimum_pair_A': float(d[np.triu_indices(50, 1)].min()),
                     'CC_A': float(d[45, 46]), 'CO_A': float(d[46, 47]), 'CH_A': float(d[45, 48]),
                     'H50_O_A': float(d[49, 47]), 'H50_Fe39_A': float(d[49, 38]),
                     'H50_Fe40_A': float(d[49, 39]),
                     'H50_nearest_Fe': int(np.argmin(d[49, :45])) + 1,
                     'H50_height_above_top_layer_A': float(a.positions[49, 2] - np.mean(a.positions[36:45, 2])),
                     'maximum_adjacent_atom_step_A': float(max(steps)),
                     'fixed_drift_A': float(max(fixed))})
        folder = EXPORT / f'{i:02d}'
        folder.mkdir()
        # Review exports only: CONTCAR is a byte copy of the final ML POSCAR,
        # never a claim that a VASP relaxation ran. No synthetic OUTCAR is made.
        for name in ['POSCAR', 'CONTCAR']:
            shutil.copyfile(OUTPUT / manifest['images'][i]['structure_path'], folder / name)
    assert all(row['minimum_pair_A'] > 1 for row in rows)
    assert all(rows[i+1]['H50_Fe39_A'] < rows[i]['H50_Fe39_A'] for i in range(4))
    assert all(rows[i+1]['H50_Fe40_A'] > rows[i]['H50_Fe40_A'] for i in range(4))
    comparison = manifest['fixed_path_model_comparison']['images']
    for row, saved in zip(comparison, manifest['images']):
        assert row['image'] == saved['image'] and row['structure_sha256'] == saved['structure_sha256']
        assert row['primary_energy_eV'] == saved['predicted_energy_eV']
    write_json_exclusive(REVIEW / 'exact_mic_geometry.json', {'method': 'ASE exact find_mic, slab xy periodic',
        'rows': rows, 'canonical_candidate_identity_geometry': 'PASS', 'endpoints_unchanged_tolerance_A': 1e-8,
        'adsorbate_connectivity_all_images': 'C2HO* + separate migrating H* retained',
        'H50_arriving_and_leaving_distances_monotonic': True})
    perl = ROOT / 'archive/vtst_review_job9745217'
    env = {**os.environ, 'PATH': 'C:/Program Files/Git/usr/bin' + os.pathsep + os.environ['PATH']}
    commands, distances = [], []
    for i in range(4):
        cmd = ['C:/Program Files/Git/usr/bin/perl.exe', '/c' + perl.as_posix()[2:] + '/dist.pl',
               f'{i:02d}/POSCAR', f'{i+1:02d}/POSCAR']
        r = subprocess.run(cmd, cwd=EXPORT, env=env, capture_output=True, text=True, check=True)
        commands.append({'command': cmd, 'exit_code': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr})
        distances.append(float(r.stdout.strip()))
    (EXPORT / 'dist.dat').write_text('\n'.join(map(str, distances)) + '\n', encoding='ascii')
    cmd = ['C:/Program Files/Git/usr/bin/perl.exe', '/c' + perl.as_posix()[2:] + '/nebmovie.pl', '1']
    r = subprocess.run(cmd, cwd=EXPORT, env=env, capture_output=True, text=True, check=True)
    commands.append({'command': cmd, 'exit_code': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr})
    with (EXPORT / 'movie.xyz').open('xb') as handle:
        for i in range(5):
            handle.write((EXPORT / f'{i:02d}/POSCAR.xyz').read_bytes())
    assert len(read(EXPORT / 'movie.xyz', index=':')) == 5
    write_json_exclusive(REVIEW / 'vtst_review.json', {'commands': commands,
        'export_semantics': 'ML final POSCAR bytes copied to CONTCAR for completed-path visualization; no VASP results',
        'movie_sha256': sha256_file(EXPORT / 'movie.xyz')})
    thresholds = ROOT / 'configs/neb_agent/default_thresholds.yaml'
    diagnosis = diagnose(EXPORT, ['45', '46', '47', '48', '49'], list(map(str, range(18))), thresholds,
                         reaction_pairs=[[49, 38], [49, 39]], expected_interior=3)
    analysis = analyze(EXPORT, thresholds, reaction_indices=list(range(45, 50)))
    assert analysis['status'] == 'NO_OUTPUT'  # ML energies never enter VASP analysis.
    anchor = atoms[0].positions[49]
    aligned = [find_mic(a.positions-anchor, a.cell, pbc=a.pbc)[0] for a in atoms]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6), layout='constrained')
    for ax, vertical, title in [(axes[0], 1, 'Top view'), (axes[1], 2, 'Side view')]:
        first = aligned[0]
        for idx in range(36, 45):
            ax.scatter(first[idx, 0], first[idx, vertical], s=200, c='#aab8c5')
            ax.annotate(f'Fe{idx+1}', (first[idx, 0], first[idx, vertical]), fontsize=8)
        for idx, color in [(45, '#333333'), (46, '#333333'), (47, '#d33c3c'), (48, '#777777')]:
            ax.scatter(first[idx, 0], first[idx, vertical], s=60, c=color)
        h = np.array([p[49] for p in aligned])
        ax.plot(h[:, 0], h[:, vertical], '-o', color='#df8500')
        for i in range(5):
            ax.annotate(str(i), (h[i, 0], h[i, vertical]), xytext=(3, -13), textcoords='offset points')
        ax.set(title=title, xlabel='x (A)', ylabel=('y' if vertical == 1 else 'z')+' (A)')
        ax.set_aspect('equal', adjustable='datalim')
    for key, label in [('primary_relative_energy_eV', 'MatRIS'), ('secondary_relative_energy_eV', 'AQCat25')]:
        axes[2].plot(range(5), [r[key] for r in comparison], '-o', label=label)
    axes[2].set(xlabel='Image', ylabel='Within-model relative energy (eV)', title='Predictions only')
    axes[2].legend()
    fig.suptitle('GPU1517: INT06 to MID | H50 surface migration | no validated TS/barrier')
    fig.savefig(REVIEW / 'path_review.png', dpi=150)
    plt.close(fig)
    print({'geometry': rows, 'canonical_geometry_status': diagnosis['status'],
           'canonical_geometry_warnings': diagnosis['warnings'], 'VASP_analysis': analysis['status']})


if __name__ == '__main__':
    main()
