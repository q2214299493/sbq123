"""No model evaluation: validate the exact six-input MatRIS direct package."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'runtime'))

from artifact_io import load_json_object, sha256_file  # noqa: E402
from aqcat25_handoff import validate_handoff  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--remote', action='store_true')
    args = parser.parse_args()
    request = load_json_object(ROOT / 'direct_request.json')
    batch = load_json_object(ROOT / 'batch_manifest.json')
    if sha256_file(ROOT / 'batch_manifest.json') != request['batch_manifest_sha256']:
        raise ValueError('batch changed')
    for row in batch['files']:
        path = (ROOT / row['path']).resolve()
        if not path.is_relative_to(ROOT.resolve()) or sha256_file(path) != row['sha256']:
            raise ValueError('stale or unsafe file: ' + row['path'])
    if args.remote:
        from matris_adsorption_relax import preflight
        checkpoint = Path(request['checkpoint_path'])
        if not checkpoint.is_file() or sha256_file(checkpoint) != request['checkpoint_sha256']:
            raise ValueError('provider checkpoint missing/changed')
        if not Path('/home/sbq/sbq/mlip_same_structure_benchmark_20260825/vendor/MatRIS/matris').is_dir():
            raise ValueError('MatRIS runtime missing')
    for row in batch['handoffs']:
        path = ROOT / row['name'] / 'handoff.json'
        if sha256_file(path) != row['handoff_sha256']:
            raise ValueError('handoff changed')
        doc = validate_handoff(path, schema_path=ROOT / 'runtime/aqcat25_handoff.schema.json')
        if doc['model']['max_steps'] != 80 or doc['model']['fmax_eV_per_A'] != 0.10:
            raise ValueError('optimizer budget changed')
        if doc['model']['checkpoint_sha256'] != request['checkpoint_sha256']:
            raise ValueError('wrong model')
        if args.remote:
            preflight(path, checkpoint, ROOT / 'runtime/aqcat25_handoff.schema.json')
    print('PASS_NO_MODEL_RUN: 6 hash-bound same-seed MatRIS candidates')


if __name__ == '__main__':
    main()
