"""No-model preflight of all fifteen frozen candidate handoffs."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'runtime'))
from artifact_io import sha256_file
from aqcat25_handoff import validate_handoff
from relax_endpoint_candidates import load_candidate

batch = json.loads((ROOT / 'batch_manifest.json').read_text(encoding='utf-8'))
assert len(batch['handoffs']) == 15
assert len({x['name'] for x in batch['handoffs']}) == 15
for item in batch['files']:
    assert sha256_file(ROOT / item['path']) == item['sha256'], item['path']
if '--remote' in sys.argv:
    assert sha256_file(Path('/home/sbq/sbq/aqcat25/demo_single/model.pt')) == batch['checkpoint_sha256']
for item in batch['handoffs']:
    directory = ROOT / item['name']
    assert sha256_file(directory / 'handoff.json') == item['handoff_sha256']
    validate_handoff(directory / 'handoff.json', root=directory,
                     schema_path=ROOT / 'runtime/aqcat25_handoff.schema.json')
    document, atoms = load_candidate(directory / 'handoff.json')
    assert len(atoms) in (49, 50)
    assert document['model']['max_steps'] == 80
    assert not (directory / 'output').exists(), 'refuse duplicate execution'
print(json.dumps({'status': 'PASS_NO_MODEL_RUN', 'candidates': 15}))
