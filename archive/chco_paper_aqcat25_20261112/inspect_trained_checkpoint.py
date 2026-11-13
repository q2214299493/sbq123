"""CPU inspection of a returned paper checkpoint; no model/trainer or acceptance.

Run inside the installed server environment after native exit evidence exists.
The final checkpoint remains a candidate, never a promoted model or valid TS.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def training_result_valid(result, request, request_sha256):
    require(result['document_kind'] == 'aqcat25_paper_single_label_training_result'
            and result['status'] == 'completed_candidate_only', 'not a completed training candidate')
    require(result['training_request_artifact_sha256'] == request_sha256
            and result['protocol_sha256'] == request['protocol_sha256']
            and result['base_checkpoint_sha256'] == request['base_checkpoint']['sha256'], 'training identity mismatch')
    evidence = result['training_evidence']
    require(all(type(evidence.get(key)) in (int, float) and evidence[key] == 100
                for key in ('completed_epochs', 'completed_steps', 'observed_optimizer_updates'))
            and evidence['optimizer_update_events'] == [{'step': i, 'epoch': float(i)} for i in range(1, 101)],
            '100 actual optimizer updates are not recorded')
    devices = evidence['execution_devices']
    require(devices['visible_cuda_device_count'] == 1 and devices['model_parameter_devices']
            and all(str(value).startswith('cuda:') for value in devices['model_parameter_devices']), 'not CUDA-only model training')
    require(all(result.get(key) is False for key in ('production_checkpoint_promotion', 'scientific_acceptance',
                'reportable_final_energy', 'reportable_barrier')), 'training result overclaims scientific acceptance')
    require(result['checkpoint']['sha256'] != result['base_checkpoint_sha256'], 'checkpoint is unchanged from base')


def inspect(args):
    import numpy as np
    import torch
    import yaml
    from ase.constraints import FixAtoms
    from ase.db import connect
    from ase.io import read

    spec = importlib.util.spec_from_file_location('inspected_paper_worker', args.worker)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    require(worker.sha256_file(args.worker) == args.worker_sha256, 'training worker changed')
    request = json.loads(worker.bound_file(args.request, args.request_sha256))
    result = json.loads(worker.bound_file(args.result, args.result_sha256))
    label, forces, movable = worker.validated_label(request)
    training_result_valid(result, request, args.request_sha256)
    output = args.result.parent.resolve(strict=True)
    root = Path('/home/sbq/sbq').resolve(strict=True)
    require(output.is_relative_to(root), 'checkpoint inspection escapes GPU work boundary')
    checkpoint = Path(result['checkpoint']['path']).resolve(strict=True)
    require(checkpoint.is_relative_to(output) and worker.sha256_file(checkpoint) == result['checkpoint']['sha256'], 'checkpoint path/hash mismatch')
    binding_path = output / 'input_binding.json'
    binding = json.loads(binding_path.read_bytes())
    require(binding['request_sha256'] == args.request_sha256 and binding['runner_sha256'] == args.worker_sha256
            and binding['label_sha256'] == request['training_samples'][0]['artifact_sha256'], 'training input binding mismatch')
    require(worker.sha256_file(output / 'training.db') == binding['database_sha256']
            and worker.sha256_file(output / 'config.yml') == binding['config_sha256'], 'training database/config changed')
    metadata = binding['dataset_metadata']
    metadata_path = Path(metadata['path']).resolve(strict=True)
    require(metadata_path == output / 'metadata.npz' and worker.sha256_file(metadata_path) == metadata['sha256']
            and metadata['sample_count'] == 1 and metadata['natoms'] == [len(forces)], 'metadata binding mismatch')
    with np.load(metadata_path, allow_pickle=False) as data:
        require(data['natoms'].tolist() == [len(forces)] and np.issubdtype(data['natoms'].dtype, np.integer), 'invalid actual sampler metadata')
    with connect(output / 'training.db') as database:
        require(database.count() == 1, 'training database is not a singleton')
        row = database.get(id=1)
        atoms = row.toatoms()
        require(row.data['source_label_sha256'] == binding['label_sha256'], 'database label identity mismatch')
    original = read(args.request.parent / 'POSCAR', format='vasp')
    require(worker.sha256_file(args.request.parent / 'POSCAR') == label['structure']['sha256']
            and atoms.get_chemical_symbols() == original.get_chemical_symbols()
            and np.allclose(atoms.positions, original.positions, atol=1e-12, rtol=0)
            and np.array_equal(atoms.get_forces(apply_constraint=False), np.asarray(forces)), 'actual training structure/forces mismatch')
    require(all(isinstance(c, FixAtoms) for c in atoms.constraints), 'unknown training constraint')
    fixed = sorted({int(i) for constraint in atoms.constraints for i in constraint.get_indices()})
    require(fixed == sorted(set(range(len(forces))) - set(movable)), 'actual training fixed mask mismatch')
    config = yaml.safe_load((output / 'config.yml').read_bytes())
    require(Path(config['dataset']['train']['metadata_path']).resolve() == metadata_path
            and Path(config['dataset']['train']['src']).resolve() == output / 'training.db', 'actual dataset configuration mismatch')
    saved = torch.load(checkpoint, map_location='cpu', weights_only=False)
    require(saved['step'] == saved['epoch'] == 100 and saved['config']['optim']['max_epochs'] == 100,
            'actual checkpoint does not record 100 completed epochs')
    tensors = [value for value in saved['state_dict'].values() if torch.is_tensor(value)]
    require(tensors and all(bool(torch.isfinite(value).all()) for value in tensors), 'checkpoint has empty/nonfinite model state')
    base = request['base_checkpoint']
    require(worker.sha256_file(Path(base['path'])) == base['sha256'], 'frozen base changed after training')
    return {'document_kind': 'paper_trained_checkpoint_CPU_inspection', 'status': 'passed_candidate_only',
        'training_result_sha256': args.result_sha256, 'training_request_sha256': args.request_sha256,
        'checkpoint': result['checkpoint'], 'checkpoint_step': saved['step'], 'checkpoint_epoch': saved['epoch'],
        'model_state_tensor_count': len(tensors), 'model_state_finite': True, 'database_sample_count': 1,
        'movable_atom_count': len(movable), 'raw_forces_and_geometry_match': True,
        'base_checkpoint_sha256': base['sha256'], 'actual_training_execution_devices': result['training_evidence']['execution_devices'],
        'inspection_device': 'cpu', 'model_constructed': False, 'trainer_constructed': False,
        'scheduler_state_established': False, 'checkpoint_promoted': False, 'TS_accepted': False,
        'inspector_source_sha256': worker.sha256_file(Path(__file__))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('worker', 'request', 'result'):
        parser.add_argument('--' + name, type=Path, required=True)
        parser.add_argument('--' + name + '-sha256', required=True)
    print(json.dumps(inspect(parser.parse_args())))


if __name__ == '__main__':
    main()
