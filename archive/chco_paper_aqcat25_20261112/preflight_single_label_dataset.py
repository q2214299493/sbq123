"""CPU-only reproduction and repair check using the installed FairChem sampler.

No trainer, model, optimizer, GPU allocation, submission or training result.
All original failed database/request/template bytes remain untouched.
"""
from __future__ import annotations

import argparse
import copy
import importlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import yaml
from ase.db import connect
from ase.io import read


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('worker', 'request', 'template', 'frozen-db', 'structure', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('worker-sha256', 'request-sha256', 'template-sha256', 'frozen-db-sha256'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('metadata_preflight_worker', args.worker)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    worker.require(worker.sha256_file(args.worker) == args.worker_sha256, 'worker changed')
    request = json.loads(worker.bound_file(args.request, args.request_sha256))
    template = yaml.safe_load(worker.bound_file(args.template, args.template_sha256))
    label, forces, movable = worker.validated_label(request)
    worker.require(worker.sha256_file(args.frozen_db) == args.frozen_db_sha256, 'frozen database changed')
    worker.bound_file(args.structure, label['structure']['sha256'])
    worker.validate_output_root(args.output)
    args.output.mkdir(parents=True, exist_ok=False)
    database_path = args.output / 'training.db'
    with args.frozen_db.open('rb') as source, database_path.open('xb') as target:
        target.write(source.read())
    with connect(database_path) as database:
        worker.require(database.count() == 1, 'preflight database is not a singleton')
        atoms = database.get(id=1).toatoms()
    original = read(args.structure, format='vasp')
    worker.require(atoms.get_chemical_symbols() == original.get_chemical_symbols()
                   and np.allclose(atoms.positions, original.positions, atol=1e-12, rtol=0)
                   and np.array_equal(atoms.get_forces(apply_constraint=False), np.asarray(forces)),
                   'copied database geometry/raw forces differ from the accepted label')
    metadata = worker.write_single_label_metadata(args.output / 'metadata.npz', len(atoms))
    config = worker.isolated_config(template, database_path)
    importlib.import_module('fairchem.core.datasets.ase_datasets')
    from fairchem.core.common.data_parallel import BalancedBatchSampler
    from fairchem.core.datasets.base_dataset import UnsupportedDatasetError, create_dataset

    def sampler(dataset):
        return BalancedBatchSampler(dataset, batch_size=1, num_replicas=1, rank=0, seed=0,
                                    mode='atoms', on_error='raise')

    bad = copy.deepcopy(config['dataset']['train'])
    bad.pop('metadata_path')
    bad['src'] = str(args.frozen_db)
    try:
        sampler(create_dataset(bad, 'train'))
    except UnsupportedDatasetError as error:
        reproduced = {'type': type(error).__name__, 'message': str(error)}
    else:
        raise ValueError('original missing-metadata failure was not reproduced')
    dataset = create_dataset(config['dataset']['train'], 'train')
    worker.require(len(dataset) == 1 and dataset.metadata_hasattr('natoms')
                   and dataset.get_metadata('natoms', [0]) == [len(atoms)], 'installed dataset did not read exact metadata')
    batches = [[int(index) for index in batch] for batch in sampler(dataset)]
    worker.require(batches == [[0]], 'installed sampler did not produce the sole training structure')
    graph = dataset[0]
    from torch_geometric.data import Batch

    batch = Batch.from_data_list([graph])
    worker.require(all(key in batch for key in config['outputs']), 'configured loss/metric targets are missing from the batch')
    worker.require(list(batch.forces.shape) == [len(atoms), 3]
                   and int((batch.fixed == 0).sum()) == len(movable)
                   and np.allclose(batch.forces.numpy(), forces, atol=1e-7, rtol=0),
                   'batched forces/free mask differ from the owner label')
    shapes = {key: list(value.shape) for key, value in graph.to_dict().items() if hasattr(value, 'shape')}
    batch_shapes = {key: list(value.shape) for key, value in batch.to_dict().items() if hasattr(value, 'shape')}
    report = {'document_kind': 'paper_single_label_dataset_CPU_preflight', 'status': 'passed',
              'training_performed': False, 'GPU_model_constructed': False, 'trainer_constructed': False,
              'original_failure_reproduced': reproduced, 'database': {'path': str(database_path), 'sha256': worker.sha256_file(database_path)},
              'metadata': metadata, 'dataset_length': len(dataset), 'sampler_batches': batches,
              'atom_count': len(atoms), 'movable_atom_count': len(movable), 'graph_tensor_shapes': shapes,
              'batch_tensor_shapes': batch_shapes, 'configured_targets_present': sorted(config['outputs']),
              'raw_request_sha256': args.request_sha256, 'worker_sha256': args.worker_sha256,
              'source_database_sha256': args.frozen_db_sha256,
              'preflight_source_sha256': worker.sha256_file(Path(__file__))}
    worker.require(worker.sha256_file(args.frozen_db) == args.frozen_db_sha256, 'original database changed during preflight')
    worker.write_json(args.output / 'preflight_result.json', report)
    print(json.dumps(report))


if __name__ == '__main__':
    main()
