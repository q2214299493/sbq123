"""Return three byte-preserved candidate outputs after native completion only."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.slurm_force_label import parse_scontrol_job

spec = importlib.util.spec_from_file_location('returned_continuation', Path(__file__).with_name('paper_continuation_job.py'))
job = importlib.util.module_from_spec(spec)
spec.loader.exec_module(job)
OUTPUTS = ('predicted_candidate.vasp', 'aqcat25_ba_sella.traj', 'candidate_report.json')


def validate_native(packet, record):
    native = packet['native_scontrol']
    if native['returncode'] != 0:
        raise ValueError('no native candidate completion query')
    parsed = parse_scontrol_job(native['stdout'], record['job_id'])
    if (packet['hostname'].split('.')[0] != 'MZ73' or parsed['job_state'] != 'COMPLETED'
            or parsed['exit_code'] != '0:0' or parsed['remote_dir'] != record['remote_dir']
            or parsed['command'] != record['remote_dir'] + '/job.sh'):
        raise ValueError('candidate job requires exact native COMPLETED / 0:0 identity')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('case-root', 'record', 'native-capture'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    case = args.case_root.resolve(strict=True)
    job.require(args.record.resolve(strict=True).parent == case, 'submission record escapes case')
    record = load_json_object(args.record)
    job.require(record['status'] == 'SUBMITTED' and record['scheduler'] == 'Slurm', 'not a known submitted candidate')
    packet = load_json_object(args.native_capture)
    validate_native(packet, record)
    receipt = load_json_object(args.native_capture.parent / 'capture_receipt.json')
    job.require(receipt['stdout_sha256'] == sha256_file(args.native_capture), 'raw native packet changed')
    manifest, backend = job.verify(job.bound(record['manifest']), record['manifest']['sha256'])
    job.require(manifest['remote_dir'] == record['remote_dir'], 'returned directory differs from reviewed manifest')
    program = '''from pathlib import Path
import hashlib,json,socket
assert socket.gethostname().split('.')[0]=='MZ73'
root=Path(__ROOT__)
assert root.resolve().is_relative_to(Path('/home/sbq/sbq').resolve(strict=True))
names=__NAMES__
result={}
for name in names:
 p=root/'output'/name
 assert p.is_file() and not p.is_symlink()
 size=p.stat().st_size
 assert 0<size<20*1024*1024
 result[name]={'bytes':size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
print(json.dumps(result))
'''.replace('__ROOT__', repr(record['remote_dir'])).replace('__NAMES__', repr(OUTPUTS))
    argv = job.primary.remote.ssh_argv(backend, shlex.join(['python3', '-B', '-c', program]))
    before = job.primary.run(argv)
    expected = json.loads(before.stdout)
    destination = case / ('return_' + record['job_id'])
    destination.mkdir(exist_ok=False)
    output = destination / 'output'
    output.mkdir()
    ssh = backend['ssh']
    copy = ['scp', *job.primary.remote._ssh_options(backend, scp=True), '--',
            *[f"{ssh['user']}@{ssh['host']}:{record['remote_dir']}/output/{name}" for name in OUTPUTS], '.']
    result = subprocess.run(copy, cwd=output, capture_output=True, check=False, timeout=60)
    if result.returncode:
        raise RuntimeError('candidate copy failed: ' + result.stderr.decode(errors='replace')[:2000])
    for name, entry in expected.items():
        job.require((output / name).stat().st_size == entry['bytes'] and sha256_file(output / name) == entry['sha256'],
                    'returned candidate bytes differ: ' + name)
    after = job.primary.run(argv)
    job.require(json.loads(after.stdout) == expected, 'candidate outputs changed during return')
    write_json_exclusive(destination / 'return_manifest.json', {
        'document_kind': 'byte_preserved_candidate_output_return', 'job_id': record['job_id'],
        'submission': job.ref(args.record), 'native_capture': job.ref(args.native_capture),
        'continuation_manifest': record['manifest'], 'remote_dir': record['remote_dir'],
        'files': expected, 'remote_unchanged_after_copy': True, 'candidate_reviewed': False,
        'scientific_TS_accepted': False})
    print(json.dumps({'returned': str(destination), 'files': expected, 'reviewed': False}))


if __name__ == '__main__':
    main()
