"""One-off immutable package builder; does not upload or start calculations."""
import copy
import csv
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive  # noqa: E402
from scripts.aqcat25_handoff import validate_handoff  # noqa: E402
from scripts.adsorption.build_fe110_adsorption import expanded_symbols, read_poscar  # noqa: E402
from scripts.adsorption.build_fe110_care_isomers import connectivity  # noqa: E402
from scripts.workflow_geometry import pbc_xy_distance  # noqa: E402

NAMES = ['06_C', '07_B', '07_C', '08_A', '09_A', '10_A']
BASE = ROOT / 'calculations/fe110_c2_adsorption_06_10_20261012'
OUTPUT = BASE / 'matris_direct_v1'
REMOTE = '/home/sbq/sbq/aqcat25_ts_pilot/fe110_c2_matris_adsorption_trial_20261018_v1'
CHECKPOINT = '/home/sbq/sbq/mlip_same_structure_benchmark_20260825/MatRIS_4M_FeCOH_compliant.pth.tar'
CHECKPOINT_SHA = '1e6a85b33db075ad1637eca7537084024a694b1340358911212d8a5c518c6601'


def build():
    if OUTPUT.exists():
        raise FileExistsError('package exists; inspect it instead of regenerating')
    OUTPUT.mkdir()
    runtime = OUTPUT / 'runtime'
    runtime.mkdir()
    for directory in ['tmp', 'cache/xdg', 'cache/torch', 'cache/huggingface']:
        (OUTPUT / directory).mkdir(parents=True)
    sources = {
        'artifact_io.py': ROOT / 'scripts/artifact_io.py',
        'direct_gpu_batch.py': ROOT / 'scripts/adsorption/direct_gpu_batch.py',
        'preflight.py': Path(__file__).with_name('preflight.py'),
        'authorization.md': Path(__file__).with_name('authorization.md'),
        'execution_backends.yaml': ROOT / 'configs/execution_backends.yaml',
        'runtime/matris_adsorption_relax.py': ROOT / 'scripts/adsorption/matris_adsorption_relax.py',
        'runtime/matris_adsorption_gpu_job.sh': ROOT / 'scripts/adsorption/matris_adsorption_gpu_job.sh',
        'runtime/mlip_same_structure_benchmark.py': ROOT / 'scripts/mlip_same_structure_benchmark.py',
        'runtime/aqcat25_handoff.py': ROOT / 'scripts/aqcat25_handoff.py',
        'runtime/aqcat25_handoff.schema.json': ROOT / 'configs/aqcat25_handoff.schema.json',
        'runtime/relax_endpoint_candidates.py': BASE / 'gpu_direct_v3/runtime/relax_endpoint_candidates.py',
    }
    for target, source in sources.items():
        shutil.copyfile(source, OUTPUT / target)
    rows = []
    for name in NAMES:
        source = BASE / 'gpu_direct_v3' / name
        old = validate_handoff(source / 'handoff.json')
        pose = read_poscar(source / 'POSCAR')
        symbols = expanded_symbols(pose)
        fixed = [i for i, flags in enumerate(pose.flags) if tuple(flags) == ('F', 'F', 'F')]
        if symbols[:45] != ['Fe'] * 45 or fixed != list(range(18)):
            raise ValueError('Fe45/fixed-mask mismatch: ' + name)
        cart = pose.frac @ pose.cell
        ads = list(range(45, len(symbols)))
        nearest = {symbols[i] + str(i): min((pbc_xy_distance(pose.cell, cart[i], cart[j]), j)
                                          for j in range(45)) for i in ads}
        if min(pair[0] for pair in nearest.values()) < 0.80:
            raise ValueError('initial emergency overlap: ' + name)
        previous = source / 'output/job_direct-fe110-c2-0610-20261013-v3/result.json'
        aqcat = load_json_object(previous)
        rows.append(dict(name=name, source_handoff_sha256=sha256_file(source / 'handoff.json'),
                         original_seed_sha256=sha256_file(source / 'POSCAR'),
                         chemical_identity=old['adsorption']['identity_and_connectivity'],
                         adsorbate_indices_zero_based=ads, initial_edges=connectivity(pose, ads),
                         nearest_fe_A_and_zero_based_index=nearest,
                         aqcat_baseline=dict(result_sha256=sha256_file(previous),
                            optimizer_steps=aqcat['optimizer_steps'],
                            final_movable_fmax_eV_per_A=aqcat['movable_fmax_eV_per_A'])))
    review = dict(reviewed_at=datetime.now(timezone.utc).isoformat(),
                  scope='same-seed provider-baseline MatRIS adsorption trial, no VASP/training/promotion',
                  reviewer='Codex, explicit user-authorized bounded experiment',
                  retrieval='Reuse six already reviewed local candidates; no external source or new motif',
                  source_candidate_review_sha256=sha256_file(BASE / 'candidates_v2/candidate_review.json'),
                  authorization_sha256=sha256_file(OUTPUT / 'authorization.md'), samples=rows,
                  optimizer=dict(name='ASE LBFGS', fmax_eV_per_A=0.1, max_steps=80,
                                 extra_bond_constraints=False),
                  scientific_acceptance=False, speedup_established=False)
    write_json_exclusive(OUTPUT / 'trial_review.json', review)
    handoffs = []
    for name in NAMES:
        source = BASE / 'gpu_direct_v3' / name
        target = OUTPUT / name
        target.mkdir()
        shutil.copyfile(source / 'POSCAR', target / 'POSCAR')
        doc = copy.deepcopy(load_json_object(source / 'handoff.json'))
        doc['handoff_id'] = 'fe110_matris_ads_trial_20261018_' + name
        doc['source_workflow_sha256'] = sha256_file(OUTPUT / 'trial_review.json')
        doc['model'] = dict(identifier='MatRIS provider baseline FeCOH 4M',
                            checkpoint_sha256=CHECKPOINT_SHA, fmax_eV_per_A=0.1, max_steps=80)
        write_json_exclusive(target / 'handoff.json', doc)
        validate_handoff(target / 'handoff.json')
        handoffs.append(dict(name=name, handoff_sha256=sha256_file(target / 'handoff.json')))
    with (OUTPUT / 'trial_status.csv').open('x', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['candidate', 'run_id', 'status', 'predicted_energy_eV', 'ML_fmax_eV_A',
                         'geometry_verdict', 'failure_reason', 'next_action'])
        for name in NAMES:
            writer.writerow([name, 'direct-fe110-matris-adsorption-20261018-v1', 'PREPARED', '', '',
                             'initial structure reviewed', '', 'explicitly authorized GPU2 trial'])
    files = [dict(path=p.relative_to(OUTPUT).as_posix(), sha256=sha256_file(p))
             for p in sorted(OUTPUT.rglob('*')) if p.is_file()]
    batch = dict(remote_root=REMOTE, checkpoint_sha256=CHECKPOINT_SHA,
                 handoffs=handoffs, files=files)
    write_json_exclusive(OUTPUT / 'batch_manifest.json', batch)
    request = dict(run_id='direct-fe110-matris-adsorption-20261018-v1',
                   exception_id='fe110_matris_adsorption_trial_20261018',
                   model_backend='matris', checkpoint_path=CHECKPOINT, checkpoint_sha256=CHECKPOINT_SHA,
                   policy=dict(path='execution_backends.yaml', sha256=sha256_file(OUTPUT / 'execution_backends.yaml')),
                   gpu_index=2, gpu_uuid='GPU-7ec6ab8a-91a2-450d-04c1-a0d472452b5b',
                   execution_mode='direct_no_scheduler', scheduler_job_id=None,
                   max_wall_seconds=1800, batch_manifest_sha256=sha256_file(OUTPUT / 'batch_manifest.json'),
                   authorization=dict(user_request='你尝试一下 授权',
                                      source_sha256=sha256_file(OUTPUT / 'authorization.md')))
    write_json_exclusive(OUTPUT / 'direct_request.json', request)
    print('PACKAGE', OUTPUT)
    print('REQUEST_SHA256', sha256_file(OUTPUT / 'direct_request.json'))


if __name__ == '__main__':
    build()
