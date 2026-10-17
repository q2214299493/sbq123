"""Deploy the reviewed immutable package and launch exactly once after preflight."""
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive  # noqa: E402

PACKAGE = ROOT / 'calculations/fe110_c2_adsorption_06_10_20261012/matris_direct_v1'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'ConnectTimeout=15',
       '-i', 'C:/Users/86177/.ssh/id_ed25519_fe_agent', '-p', '36039', 'sbq@10sx4jr711576.vicp.fun']
SCP = ['scp', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'ConnectTimeout=15',
       '-i', 'C:/Users/86177/.ssh/id_ed25519_fe_agent', '-P', '36039']
REMOTE_PYTHON = '/home/sbq/sbq/ml_ts_acceleration/venv/bin/python'


def call(args, *, code=None, timeout=60):
    process = subprocess.run(args, input=code.encode() if code else None, capture_output=True, timeout=timeout)
    print(process.stdout.decode('utf-8', 'replace')[:5000], flush=True)
    if process.stderr:
        print(process.stderr.decode('utf-8', 'replace')[:3000], flush=True)
    if process.returncode:
        raise RuntimeError('command failed with exit ' + str(process.returncode))
    return process


def main():
    request = load_json_object(PACKAGE / 'direct_request.json')
    batch = load_json_object(PACKAGE / 'batch_manifest.json')
    remote = batch['remote_root']
    remote_archive = remote + '.tar.gz'
    digest = sha256_file(PACKAGE / 'direct_request.json')
    if (PACKAGE / 'deployment_started.json').exists():
        raise FileExistsError('deployment already attempted; inspect remote receipts instead of retrying')
    paths = [r['path'] for r in batch['files']] + ['batch_manifest.json', 'direct_request.json']
    for row in batch['files']:
        if sha256_file(PACKAGE / row['path']) != row['sha256']:
            raise ValueError('local package changed: ' + row['path'])
    if sha256_file(PACKAGE / 'batch_manifest.json') != request['batch_manifest_sha256']:
        raise ValueError('local batch changed')
    inspect = r'''
import socket,subprocess
from pathlib import Path
root=Path(REMOTE)
boundary=Path('/home/sbq/sbq').resolve()
if socket.gethostname()!='MZ73' or not root.resolve().is_relative_to(boundary):
    raise RuntimeError('unexpected host/boundary')
if root.exists() or Path(ARCHIVE).exists():
    raise FileExistsError('remote deployment already exists')
lines=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.free','--format=csv,noheader,nounits'],timeout=10).decode().splitlines()
matches=[x.split(',') for x in lines if x.split(',')[1].strip()==UUID]
if len(matches)!=1 or int(matches[0][0])!=2 or int(matches[0][2])<20000:
    raise RuntimeError('authorized GPU2 unavailable')
processes=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader'],timeout=10).decode()
if any(x.split(',')[0].strip()==UUID for x in processes.splitlines()):
    raise RuntimeError('GPU2 already has a compute process; nothing stopped')
print('REMOTE_NEW_TARGET_AND_IDLE_GPU2_PASS_NO_MODEL_RUN')
'''
    prefix = 'REMOTE=' + repr(remote) + '\nARCHIVE=' + repr(remote_archive) + '\nUUID=' + repr(request['gpu_uuid']) + '\n'
    call(SSH + [REMOTE_PYTHON + ' -'], code=prefix + inspect, timeout=30)
    archive = Path(__file__).with_name('payload.tar.gz')
    if archive.exists():
        raise FileExistsError(archive)
    with tarfile.open(archive, 'x:gz') as tar:
        for name in paths:
            tar.add(PACKAGE / name, arcname=name, recursive=False)
    write_json_exclusive(PACKAGE / 'deployment_started.json', dict(
        remote_root=remote, request_sha256=digest, archive_sha256=sha256_file(archive),
        execution_mode='direct_no_scheduler', scheduler_job_id=None))
    call(SCP + [str(archive), 'sbq@10sx4jr711576.vicp.fun:' + remote_archive], timeout=45)
    extract = r'''
import hashlib,tarfile
from pathlib import Path
root=Path(REMOTE)
archive=Path(ARCHIVE)
if hashlib.sha256(archive.read_bytes()).hexdigest()!=ARCHIVE_SHA:
    raise ValueError('deployment archive changed')
if not root.resolve().is_relative_to(Path('/home/sbq/sbq').resolve()):
    raise ValueError('deployment escapes boundary')
root.mkdir(exist_ok=False)
with tarfile.open(archive) as tar:
    for member in tar.getmembers():
        target=root/member.name
        if not member.isfile() or not target.resolve().is_relative_to(root.resolve()):
            raise ValueError('unsafe archive member')
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as f:f.write(tar.extractfile(member).read())
for directory in ['tmp','cache/xdg','cache/torch','cache/huggingface']:
    (root/directory).mkdir(parents=True,exist_ok=True)
print('REMOTE_HASH_BOUND_EXTRACTION_PASS')
'''
    call(SSH + [REMOTE_PYTHON + ' -'], code=prefix + 'ARCHIVE_SHA=' + repr(sha256_file(archive)) + '\n' + extract, timeout=30)
    command = (REMOTE_PYTHON + ' ' + remote + '/direct_gpu_batch.py preflight ' + remote +
               '/direct_request.json --request-sha256 ' + digest)
    process = call(SSH + [command], timeout=60)
    (PACKAGE / 'remote_preflight.stdout.txt').write_bytes(process.stdout)
    write_json_exclusive(PACKAGE / 'remote_preflight_record.json', dict(
        exit_code=process.returncode, request_sha256=digest, model_run=False,
        stdout_sha256=sha256_file(PACKAGE / 'remote_preflight.stdout.txt')))
    command = command.replace(' preflight ', ' launch ')
    # Never repeat this call after an ambiguous result. Launch reserves a marker
    # before forking, and the canonical remote receipt is collected below.
    call(SSH + [command], timeout=60)
    call(SCP + ['sbq@10sx4jr711576.vicp.fun:' + remote + '/direct_launch_receipt.json',
                str(PACKAGE / 'direct_launch_receipt.json')], timeout=30)
    print('CANONICAL_LAUNCH_RECEIPT_COLLECTED', flush=True)


if __name__ == '__main__':
    main()
