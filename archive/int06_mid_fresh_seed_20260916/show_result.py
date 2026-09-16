"""Render actual job 1635 outputs; no model execution or scientific acceptance."""
import csv
import os
import shutil
import subprocess

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from ase.geometry import find_mic
from ase.io import read

from archive.int06_mid_fresh_seed_20260916.prepare import ROOT, DEST
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive


def main():
    source = DEST / 'returned_job1635/production'
    output = DEST / 'review_job1635'
    output.mkdir(exist_ok=True)
    assert not (output / 'geometry_and_provenance.json').exists(), 'Review already completed'
    manifest = load_json_object(source / 'dual_model_gpu_ml_neb_path_manifest.candidate.json')
    assert manifest['source_request']['sha256'] == sha256_file(DEST / 'submission_20260916/payload/request.json')
    assert sha256_file(source / 'producer_exit_record.json') == manifest['producer_exit_record']['sha256']
    frames, rows = [], []
    for row in manifest['images']:
        path = source / row['structure_path']
        assert sha256_file(path) == row['structure_sha256']
        atoms = read(path, format='vasp')
        atoms.pbc = [True, True, False]
        assert len(atoms) == 50
        frames.append(atoms)
        folder = output / row['image']
        folder.mkdir(exist_ok=True)
        for name in ['CONTCAR', 'POSCAR']:
            if (folder / name).exists():
                assert sha256_file(folder / name) == sha256_file(path)
            else:
                shutil.copyfile(path, folder / name)
    for i, atoms in enumerate(frames):
        assert atoms.get_chemical_symbols() == frames[0].get_chemical_symbols()
        assert np.allclose(atoms.cell, frames[0].cell, rtol=0, atol=1e-8)
        assert np.array_equal(atoms.constraints[0].get_indices(), np.arange(18))
        assert np.max(np.abs(atoms.positions[:18] - frames[0].positions[:18])) < 1e-8
        d = atoms.get_all_distances(mic=True)
        raw = atoms.positions - frames[max(0, i - 1)].positions
        mic, lengths = find_mic(raw, atoms.cell, pbc=atoms.pbc)
        assert np.max(np.abs(raw - mic)) < 1e-7
        def nearest(idx):
            return int(np.argmin(d[idx, :45]))
        rows.append(dict(image=f'{i:02d}',
            MatRIS_relative_eV=manifest['images'][i]['predicted_energy_eV']-manifest['images'][0]['predicted_energy_eV'],
            NEB_force_eVA=manifest['images'][i]['projected_neb_force_max_eVA'],
            CC_A=d[45, 46], CO_A=d[46, 47], OH_A=d[47, 49],
            H50_Fe39_A=d[49, 38], H50_Fe40_A=d[49, 39],
            C1_nearest_Fe=nearest(45)+1, C1_Fe_A=d[45, nearest(45)],
            C2_nearest_Fe=nearest(46)+1, C2_Fe_A=d[46, nearest(46)],
            O_nearest_Fe=nearest(47)+1, O_Fe_A=d[47, nearest(47)],
            H50_nearest_Fe=nearest(49)+1, H50_Fe_A=d[49, nearest(49)],
            min_pair_A=d[np.triu_indices(50, 1)].min(), max_adjacent_atom_step_A=max(lengths)))
    for frame, name in ((frames[0], 'IS.vasp'), (frames[-1], 'FS.vasp')):
        original = read(DEST / name)
        _, lengths = find_mic(frame.positions-original.positions, frame.cell, pbc=frame.pbc)
        assert max(lengths) < 1e-8
    perl = ROOT / 'archive/vtst_review_job9745217'
    env = {**os.environ, 'PATH': 'C:/Program Files/Git/usr/bin'+os.pathsep+os.environ['PATH']}
    commands = []
    for args in [('dist.pl', f'{i:02d}/CONTCAR', f'{i+1:02d}/CONTCAR') for i in range(8)] + [('nebmovie.pl', '1')]:
        script = '/c'+(perl / args[0]).as_posix()[2:]
        run = subprocess.run(['C:/Program Files/Git/usr/bin/perl.exe', script, *args[1:]],
                             cwd=output, env=env, capture_output=True, text=True, check=True)
        commands.append(dict(args=list(args), exit_code=run.returncode, stdout=run.stdout, stderr=run.stderr))
    # This VTST version deliberately removes its combined XYZ (xyzflag=0).
    # Preserve the generated per-frame files as one verified portable movie.
    with (output / 'movie.xyz').open('xb') as handle:
        for i in range(9):
            handle.write((output / f'{i:02d}/POSCAR.xyz').read_bytes())
    movie = read(output / 'movie.xyz', index=':', format='xyz')
    assert len(movie) == 9
    for a, b in zip(frames, movie):
        assert np.max(np.abs(a.positions-b.positions)) < 2e-5
    write_json_exclusive(output / 'geometry_and_provenance.json', dict(
        manifest_sha256=sha256_file(source / 'dual_model_gpu_ml_neb_path_manifest.candidate.json'),
        rows=rows, vtst=commands, status='numeric_checks_passed_not_scientific_acceptance'))
    with (output / 'image_metrics.csv').open('x', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    render(frames, rows, manifest, output)


def render(frames, rows, manifest, output):
    compare = manifest['fixed_path_model_comparison']['images']
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.2), layout='constrained')
    for key, label, color in [('primary_relative_energy_eV', 'MatRIS (path optimizer)', '#16669a'),
                              ('secondary_relative_energy_eV', 'AQCat25 (same structures)', '#b36122')]:
        axes[0].plot(range(9), [r[key] for r in compare], '-o', label=label, color=color)
    axes[0].axvspan(3.8, 5.2, color='#f5be4f', alpha=.15)
    axes[0].set(ylabel='Within-model E(image) - E(00) / eV', title='ML energy profiles - not a DFT barrier')
    axes[0].legend(fontsize=8)
    axes[1].plot(range(1, 8), [r['NEB_force_eVA'] for r in rows[1:8]], '-o', color='#29734d', label='Projected NEB force')
    axes[1].axhline(.1, color='#bd3939', linestyle='--', label='Requested 0.10 eV/A')
    axes[1].set(ylabel='Maximum internal NEB force / eV/A', title='19 optimization steps; ordinary NEB')
    axes[1].legend(fontsize=8)
    for ax in axes:
        ax.set(xlabel='Image', xticks=range(9), xticklabels=[f'{i:02d}' for i in range(9)])
        ax.grid(alpha=.18)
    fig.savefig(output / 'energy_force.png', dpi=170)
    plt.close(fig)

    # One fixed periodic branch and identical limits for every structural panel.
    anchor = frames[0].positions[49]
    raw0 = frames[0].positions-anchor
    mapped0 = find_mic(raw0, frames[0].cell, pbc=frames[0].pbc)[0]
    # Keep the C2HO fragment whole rather than wrap each bonded atom separately.
    for child, parent in [(46, 47), (45, 46), (48, 45)]:
        mapped0[child] = mapped0[parent] + find_mic(raw0[child]-raw0[parent], frames[0].cell, pbc=frames[0].pbc)[0]
    offset = raw0-mapped0
    positions = [a.positions-anchor-offset for a in frames]
    for atoms, p in zip(frames, positions):
        for a, b in [(45, 46), (46, 47), (45, 48)]:
            assert abs(np.linalg.norm(p[a]-p[b])-atoms.get_distance(a, b, mic=True)) < 1e-8
    hpath = np.array([p[49] for p in positions])
    active = np.concatenate([p[45:] for p in positions])
    xlim = (min(active[:, 0].min(), hpath[:, 0].min())-.9, max(active[:, 0].max(), hpath[:, 0].max())+.9)
    ylim = (min(active[:, 1].min(), hpath[:, 1].min())-.9, max(active[:, 1].max(), hpath[:, 1].max())+.9)

    def draw(ax, idx):
        p = positions[idx]
        for j in range(36, 45):
            ax.scatter(p[j, 0], p[j, 1], s=330, color='#bec7d1', edgecolor='#8b97a5', zorder=1)
            if xlim[0] < p[j, 0] < xlim[1] and ylim[0] < p[j, 1] < ylim[1]:
                ax.annotate(f'Fe{j+1}', p[j, :2], xytext=(0, -14), textcoords='offset points', ha='center', fontsize=7)
        ax.plot(hpath[:, 0], hpath[:, 1], '--', color='#dc9f58', linewidth=1, alpha=.7)
        for a, b in [(45, 46), (46, 47), (45, 48)]:
            ax.plot(p[[a, b], 0], p[[a, b], 1], color='#4f5864', linewidth=2, zorder=2)
        for j, color, size, label in [(45, '#343d49', 85, 'C1'), (46, '#343d49', 85, 'C2'),
                                      (47, '#c53e43', 100, 'O'), (48, '#e8e8e8', 55, 'H49'),
                                      (49, '#f28b22', 100, 'H50')]:
            ax.scatter(p[j, 0], p[j, 1], s=size, color=color, edgecolor='#333333', linewidth=.5, zorder=4)
            ax.annotate(label, p[j, :2], xytext=(6, 6), textcoords='offset points', fontsize=8, zorder=5)
        ax.set(xlim=xlim, ylim=ylim, aspect='equal')
        ax.set_title(f"{idx:02d} | H50-Fe39 {rows[idx]['H50_Fe39_A']:.2f} A | dE {rows[idx]['MatRIS_relative_eV']:+.3f} eV", fontsize=9)
        ax.set_xticks([])
        ax.set_yticks([])

    fig, axes = plt.subplots(3, 3, figsize=(12, 8), layout='constrained')
    for i, ax in enumerate(axes.flat):
        draw(ax, i)
    fig.suptitle('Job 1635 | actual optimized images 00-08 | top view\nOrange: migrating H50; grey: top-layer Fe; red: O; same scale and PBC branch', fontsize=12)
    fig.savefig(output / 'structures_00_08.png', dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), layout='constrained')
    for ax, i in zip(axes, [4, 5, 6]):
        draw(ax, i)
    fig.suptitle('Peak neighborhood 04-05-06 | ML candidates, not validated TS')
    fig.savefig(output / 'peak_04_06.png', dpi=180)
    plt.close(fig)
    print(output)
    print('MatRIS 05-04 energy difference / eV:', rows[5]['MatRIS_relative_eV']-rows[4]['MatRIS_relative_eV'])
    print('AQCat relative energies:', [round(r['secondary_relative_energy_eV'], 6) for r in compare])


if __name__ == '__main__':
    main()
