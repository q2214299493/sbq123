"""Submit the corrected request once on scheduler-assigned physical GPU0."""
import argparse
import json
import shutil
from datetime import datetime, timezone

from archive.int06_mid_gpu_20260910 import gpu1_envfix as envfix
from archive.int06_mid_gpu_20260910 import gpu1_checkpoint as checkpoint
from archive.int06_mid_gpu_20260910.inspect_remote import BASE
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive

attempt = envfix.attempt
attempt.ATTEMPT = BASE / 'attempt_gpu0_20260910'
attempt.REMOTE_ATTEMPT = attempt.REMOTE + '_gpu0'
UUID = 'GPU-483c224e-cc19-13e2-24ad-c83efd14fa75'


def prepare():
    prior = BASE / 'attempt_gpu1_ready_20260910'
    local = attempt.ATTEMPT
    local.mkdir(exist_ok=False)
    shutil.copytree(prior / 'payload_updates', local / 'payload_updates')
    # Manifest metadata names the new immutable attempt. Request bytes stay exact.
    manifest = load_json_object(local / 'payload_updates/payload_manifest.json')
    manifest['remote_root'] = attempt.REMOTE_ATTEMPT
    (local / 'payload_updates/payload_manifest.json').write_text(
        json.dumps(manifest, indent=2) + '\n', encoding='utf-8', newline='\n')
    execution = local / 'execution'
    execution.mkdir()
    driver = (prior / 'execution/submit_remote.py').read_text(encoding='utf-8')
    driver = driver.replace('提交gpu1', '提交gpu0').replace('user_requested_gpu1_attempt', 'user_requested_gpu0_attempt')
    driver = driver.replace('int06-mid-gpu1', 'int06-mid-gpu0')
    (execution / 'submit_remote.py').write_text(driver, encoding='utf-8', newline='\n')
    guard = (prior / 'execution/allocated_gpu_guard.sh').read_text(encoding='utf-8')
    guard = guard.replace('GPU-450609b3-d1fd-ac33-d03a-79891be402da', UUID)
    guard = guard.replace("idx=='1'", "idx=='0'").replace("'physical_index':1", "'physical_index':0")
    guard = guard.replace("os.environ.get('SLURM_JOB_GPUS')=='1'", "os.environ.get('SLURM_JOB_GPUS')=='0'")
    guard = guard.replace('GPU1', 'GPU0')
    guard = guard.replace("job=os.environ['SLURM_JOB_ID']",
                          "job=os.environ['SLURM_JOB_ID']\nassert os.environ.get('SLURM_JOB_GPUS')=='0', 'scheduler must allocate physical GPU0'")
    (execution / 'allocated_gpu_guard.sh').write_text(guard, encoding='utf-8', newline='\n')
    auth = load_json_object(prior / 'execution/authorization.json')
    auth.update(user_instruction='提交gpu0', action='user_requested_gpu0_attempt',
                authorized_at=datetime.now(timezone.utc).isoformat(), remote_root=attempt.REMOTE_ATTEMPT,
                target_gpu_uuid=UUID, target_physical_gpu_index=0, prior_failed_job='1516',
                driver_sha256=sha256_file(execution / 'submit_remote.py'),
                guard_sha256=sha256_file(execution / 'allocated_gpu_guard.sh'),
                payload_manifest_sha256=sha256_file(local / 'payload_updates/payload_manifest.json'),
                scope='One corrected ML-NEB launch on explicitly requested GPU0, requiring matching scheduler allocation; same 1 GPU, 4 CPUs, 40GB, 6h, 400 steps; no automatic retries or VASP submission.')
    assert sha256_file(local / 'payload_updates/request.json') == auth['request_sha256']
    write_json_exclusive(execution / 'authorization.json', auth)
    print('GPU0 attempt prepared; corrected request bytes unchanged; scheduler allocation must match')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['prepare', 'stage', 'check', 'submit', 'checkpoint'])
    mode = parser.parse_args().mode
    if mode == 'prepare':
        prepare()
    elif mode == 'stage':
        envfix.stage()
    elif mode == 'checkpoint':
        checkpoint.main()
    else:
        attempt.run(mode)
