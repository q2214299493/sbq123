"""MatRIS adsorption trial adapter; reuses the reviewed endpoint geometry helpers."""
from __future__ import annotations

import argparse
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

try:
    from scripts.artifact_io import sha256_file, write_json_exclusive
    from scripts.aqcat25_handoff import validate_handoff
    from scripts.adsorption.direct_gpu_batch import cuda_binding
    from scripts.mlip_same_structure_benchmark import _load_calculator
except ModuleNotFoundError:
    from artifact_io import sha256_file, write_json_exclusive
    from aqcat25_handoff import validate_handoff
    from direct_gpu_batch import cuda_binding
    from mlip_same_structure_benchmark import _load_calculator


def preflight(handoff: Path, checkpoint: Path, schema: Path) -> dict:
    document = validate_handoff(handoff, schema_path=schema)
    if document['direction'] != 'work_to_gpu' or document['workflow_kind'] != 'adsorption':
        raise ValueError('MatRIS adapter accepts adsorption work-to-GPU inputs only')
    if not document['model']['identifier'].startswith('MatRIS '):
        raise ValueError('not a MatRIS handoff')
    if not checkpoint.is_file():
        raise FileNotFoundError('MatRIS checkpoint missing')
    if sha256_file(checkpoint) != document['model']['checkpoint_sha256']:
        raise ValueError('MatRIS checkpoint hash mismatch')
    return document


def run(handoff: Path, checkpoint: Path, output: Path, run_id: str, schema: Path) -> None:
    from ase.io import write
    from ase.optimize import LBFGS
    # Frozen and hash-bound copy of the original AQCat endpoint helper; no
    # Fairchem import or AQCat evaluation is performed by these three helpers.
    from relax_endpoint_candidates import geometry_snapshot, evaluate_connectivity, load_candidate
    import torch

    document = preflight(handoff, checkpoint, schema)
    if not checkpoint.is_file() or not torch.cuda.is_available():
        raise RuntimeError('MatRIS checkpoint and CUDA are required; no CPU fallback')
    if socket.gethostname() != 'MZ73':
        raise RuntimeError('MatRIS trial must run on MZ73')
    if output.exists():
        raise FileExistsError('candidate output already exists; inspect instead of rerunning')
    output.mkdir(parents=True)
    started = datetime.now(timezone.utc).isoformat()
    code, error = 1, 'incomplete producer'
    try:
        _, atoms = load_candidate(handoff)
        symbols = atoms.get_chemical_symbols()
        fixed = np.asarray(document['selective_dynamics']['fixed_atom_indices_1based']) - 1
        cell, positions = atoms.cell.array.copy(), atoms.positions.copy()
        before = geometry_snapshot(atoms, document['adsorption'])
        atoms.calc = _load_calculator('matris', checkpoint, 'cuda')
        write_json_exclusive(output / 'execution_device.json', cuda_binding(atoms.calc))
        surface = np.array([i for i, s in enumerate(symbols) if s == 'Fe'])
        adsorbate = np.array([i for i, s in enumerate(symbols) if s != 'Fe'])

        def checked_forces():
            forces = np.asarray(atoms.get_forces(apply_constraint=False), dtype=float)
            if forces.shape != (len(atoms), 3) or not np.isfinite(forces).all():
                raise RuntimeError('nonfinite or incomplete MatRIS forces')
            if not np.isfinite(atoms.positions).all():
                raise RuntimeError('nonfinite MatRIS coordinates')
            contacts = atoms.get_all_distances(mic=True)[np.ix_(surface, adsorbate)]
            if contacts.min() < 0.80:
                raise RuntimeError('emergency Fe-adsorbate overlap below project 0.80 A limit')
            if not np.allclose(atoms.positions[fixed], positions[fixed], atol=1e-8, rtol=0):
                raise RuntimeError('fixed-layer coordinates changed')
            return forces

        initial_forces = checked_forces()
        optimizer = LBFGS(atoms, logfile=str(output / 'optimizer.log'),
                          trajectory=str(output / 'optimization.traj'))
        optimizer.attach(checked_forces, interval=1)
        converged = bool(optimizer.run(fmax=document['model']['fmax_eV_per_A'],
                                       steps=document['model']['max_steps']))
        forces = checked_forces()
        free = np.ones(len(atoms), dtype=bool)
        free[fixed] = False
        fmax = float(np.linalg.norm(forces[free], axis=1).max())
        energy = float(atoms.get_potential_energy())
        if not np.isfinite(energy):
            raise RuntimeError('nonfinite MatRIS energy')
        invariants = dict(atom_order_preserved=atoms.get_chemical_symbols() == symbols,
                          cell_preserved=bool(np.allclose(atoms.cell.array, cell, atol=1e-10, rtol=0)),
                          fixed_atoms_preserved=bool(np.allclose(atoms.positions[fixed], positions[fixed],
                                                                atol=1e-8, rtol=0)))
        if not all(invariants.values()):
            raise RuntimeError('atom order, cell or fixed layer changed')
        connectivity = evaluate_connectivity(atoms, document['adsorption'])
        write(output / 'POSCAR', atoms, format='vasp', direct=True, vasp5=True)
        (output / 'source_handoff.json').write_bytes(handoff.read_bytes())
        write_json_exclusive(output / 'forces.json', dict(symbols=symbols,
                             fixed_atom_indices_zero_based=fixed.tolist(),
                             initial_forces_eV_per_A=initial_forces.tolist(),
                             final_forces_eV_per_A=forces.tolist(), predicted_only=True))
        result = dict(handoff_id=document['handoff_id'], converged=converged,
                      optimizer_steps=int(optimizer.nsteps), energy_eV=energy,
                      movable_fmax_eV_per_A=fmax, geometry_before=before,
                      geometry_after=geometry_snapshot(atoms, document['adsorption']),
                      connectivity=connectivity, structure_invariants=invariants)
        write_json_exclusive(output / 'result.json', result)
        code, error = 0, None
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        write_json_exclusive(output / 'producer_exit_record.json', dict(
            gpu_job_id=run_id, hostname=socket.gethostname(), started_utc=started,
            finished_utc=datetime.now(timezone.utc).isoformat(), exit_code=code,
            status='success' if code == 0 else 'failed', error=error,
            evidence_class='producer_process_only_not_scheduler_accounting'))
    returned = dict(schema_version=2, direction='gpu_to_work', workflow_kind='adsorption',
                    handoff_id=document['handoff_id'],
                    source_workflow_sha256=document['source_workflow_sha256'],
                    source_handoff=dict(path='source_handoff.json', sha256=sha256_file(handoff)),
                    candidate_structure=dict(document['candidate_structure'], path='POSCAR',
                                             sha256=sha256_file(output / 'POSCAR')),
                    adsorption=document['adsorption'],
                    producer=dict(backend='aqcat_gpu', hostname=socket.gethostname(), gpu_job_id=run_id,
                                  model_identifier=document['model']['identifier'],
                                  checkpoint_sha256=sha256_file(checkpoint)),
                    result=dict(result_class='predicted_adsorption_candidate_only',
                                optimizer_status='converged' if converged else 'unfinished',
                                optimizer_steps=result['optimizer_steps'],
                                predicted_energy=dict(value=energy, unit='eV', reportable_dft=False),
                                predicted_force=dict(fmax=fmax, unit='eV/A', reportable_dft=False),
                                geometry_before=before, geometry_after=result['geometry_after'],
                                connectivity_status=connectivity['status'], structure_invariants=invariants),
                    domain_assessment=dict(calibration_id=None, status='uncalibrated',
                                           method='scoped MatRIS adsorption trial, not a calibrated ranking',
                                           reasons=['No new-pose VASP validation or speedup measurement yet']),
                    producer_exit_record=dict(path='producer_exit_record.json',
                        sha256=sha256_file(output / 'producer_exit_record.json'), status='success',
                        exit_code=0, evidence_class='producer_process_only_not_scheduler_accounting'),
                    restrictions=document['restrictions'])
    write_json_exclusive(output / 'gpu_result_manifest.json', returned)
    validate_handoff(output / 'gpu_result_manifest.json', schema_path=schema)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--handoff', type=Path, required=True)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--run-id')
    parser.add_argument('--schema', type=Path, default=Path(__file__).with_name('aqcat25_handoff.schema.json'))
    parser.add_argument('--preflight', action='store_true')
    args = parser.parse_args()
    if args.preflight:
        preflight(args.handoff, args.checkpoint, args.schema)
        print('PASS_NO_MODEL_RUN')
    else:
        if args.output is None or args.run_id is None:
            parser.error('--output and --run-id required for execution')
        run(args.handoff, args.checkpoint, args.output, args.run_id, args.schema)


if __name__ == '__main__':
    sys.exit(main())
