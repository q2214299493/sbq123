"""Run bounded geometry/VTST checks on the new local path and render review views."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import matplotlib
import numpy as np
from ase.geometry import find_mic
from ase.io import read

from scripts.adsmind_lite.relaxed_analysis import connectivity_edges
from scripts.artifact_io import sha256_file, write_json_exclusive
from scripts.vasp_inputs import build_fe110_neb

matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT/'calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_migration_int06_to_mid_path_20260910'
PATH = BASE/'plan/path_candidate'


def main() -> None:
    assert PATH.is_relative_to(BASE) and not (PATH/'movie').exists()
    perl = Path('C:/Program Files/Git/usr/bin/perl.exe')
    vtst = ROOT/'archive/vtst_review_job9745217'
    # Git's MSYS Perl needs a POSIX script path for FindBin's sibling Vasp.pm.
    vtst_posix = '/c'+vtst.as_posix()[2:]
    env = {**os.environ,'PATH':str(perl.parent)+os.pathsep+os.environ['PATH']}
    dist_lines, commands = [], []
    for i in range(4):
        command = [str(perl),vtst_posix+'/dist.pl',f'{i:02d}/POSCAR',f'{i+1:02d}/POSCAR']
        r = subprocess.run(command,cwd=PATH,env=env,capture_output=True,text=True,check=True)
        value = float(r.stdout.strip())
        dist_lines.append(f'{i:02d} {i+1:02d} {value:.12f}')
        commands.append({'command':command,'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
    (PATH/'dist.dat').write_text('\n'.join(dist_lines)+'\n',encoding='ascii')
    command = [str(perl),vtst_posix+'/nebmovie.pl','0']
    r = subprocess.run(command,cwd=PATH,env=env,capture_output=True,text=True,check=True)
    commands.append({'command':command,'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
    assert (PATH/'movie').stat().st_size>0
    # This VTST version removes combined XYZ by default; preserve its per-image output.
    with (PATH/'movie.xyz').open('xb') as handle:
        for i in range(5):
            handle.write((PATH/f'{i:02d}/POSCAR.xyz').read_bytes())
    frames = [read(PATH/f'{i:02d}/POSCAR',format='vasp') for i in range(5)]
    rows = []
    for i,a in enumerate(frames):
        a.pbc=(True,True,False)
        d=a.get_all_distances(mic=True)
        _,fixed=find_mic(a.positions[:18]-frames[0].positions[:18],a.cell,pbc=a.pbc)
        assert max(fixed)<1e-8
        assert connectivity_edges(a,list(range(45,50)),1.25,0.35)==[(0,1),(0,3),(1,2)]
        _,moves=find_mic(a.positions-frames[max(i-1,0)].positions,a.cell,pbc=a.pbc)
        rows.append({'image':f'{i:02d}','minimum_distance_A':float(d[np.triu_indices(50,1)].min()),
                     'CC_A':float(d[45,46]),'CO_A':float(d[46,47]),'CH_A':float(d[45,48]),'OH_A':float(d[47,49]),
                     'H50_Fe39_A':float(d[49,38]),'H50_Fe40_A':float(d[49,39]),
                     'max_adjacent_step_A':float(max(moves)),'fixed_max_drift_A':float(max(fixed)),
                     'sha256':sha256_file(PATH/f'{i:02d}/POSCAR')})
    assert all(r['minimum_distance_A']>1.0 for r in rows)
    assert all(rows[i+1]['H50_Fe39_A']<rows[i]['H50_Fe39_A'] for i in range(4))
    assert all(rows[i+1]['H50_Fe40_A']>rows[i]['H50_Fe40_A'] for i in range(4))
    write_json_exclusive(PATH/'exact_mic_geometry.json',{'rows':rows,'method':'ASE find_mic, slab xy PBC',
                         'checks':'identical C2HO connectivity, fixed layers, no collision, monotone arriving/leaving Fe distances'})
    write_json_exclusive(PATH/'vtst_commands.json',{'commands':commands,'movie_sha256':sha256_file(PATH/'movie'),
                         'dist_script_sha256':sha256_file(vtst/'dist.pl'),'nebmovie_script_sha256':sha256_file(vtst/'nebmovie.pl')})
    anchor=frames[0].positions[49]
    aligned=[find_mic(a.positions-anchor,a.cell,pbc=a.pbc)[0] for a in frames]
    fig,axes=plt.subplots(1,2,figsize=(11,4.5),layout='constrained')
    for ax,vertical,title in [(axes[0],1,'Top view'),(axes[1],2,'Side view')]:
        p=aligned[0]
        for idx in range(36,45):
            ax.scatter(p[idx,0],p[idx,vertical],s=210,color='#b8c1cc',edgecolor='white')
            ax.annotate(f'Fe{idx+1}',(p[idx,0],p[idx,vertical]),fontsize=8,xytext=(3,4),textcoords='offset points')
        for idx,color in [(45,'#333333'),(46,'#333333'),(47,'#de5c50'),(48,'#777777')]:
            ax.scatter(p[idx,0],p[idx,vertical],s=65,color=color)
        h=np.array([v[49] for v in aligned])
        ax.plot(h[:,0],h[:,vertical],'-o',color='#ef8d23',linewidth=2,markersize=8)
        for i,(x,y) in enumerate(zip(h[:,0],h[:,vertical])):
            ax.annotate(str(i),(x,y),xytext=(3,-14),textcoords='offset points',fontsize=9)
        ax.set(xlabel='x relative to initial H50 (Å)',ylabel=('y' if vertical==1 else 'z')+' (Å)',title=title)
        ax.set_aspect('equal',adjustable='datalim')
        ax.grid(alpha=.2)
    fig.suptitle('INT06 → MID: H50 path 0–4 | initial geometry only, no TS claim')
    fig.savefig(BASE/'path_review.png',dpi=180)
    plt.close(fig)
    assert not (PATH/'INCAR').exists()
    inputs=build_fe110_neb(PATH,images=3,cores=96)
    write_json_exclusive(PATH/'input_builder.json',inputs)
    print(json.dumps({'geometry':rows,'vtst_exit_codes':[r['exit_code'] for r in commands],
                      'movie_bytes':(PATH/'movie').stat().st_size,'cores':inputs['cores']},indent=2))


if __name__=='__main__':
    main()
