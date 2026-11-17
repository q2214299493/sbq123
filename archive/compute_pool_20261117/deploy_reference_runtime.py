"""Relay the verified software bundle through local SSH, never copying keys."""
import concurrent.futures
import datetime
import json
import pathlib
import subprocess

ROOT = '/home/sbq/sbq/compute_pool_20261117'
SHA = '781b107cc851983ee566c5c7d4b04a90eca5a64fe218b3b5cd4a02691daa6b75'
BASE = ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'IdentitiesOnly=yes', '-o', 'Compression=no', '-o', 'ServerAliveInterval=20', '-o', 'ServerAliveCountMax=3']
IDENTITY = ['-i', 'C:/Users/86177/.ssh/id_ed25519_fe_agent']
SOURCE = BASE + IDENTITY + ['-p', '36039', 'sbq@10sx4jr711576.vicp.fun']
TARGETS = {'BUCT2': BASE + ['buct2-gpu'], 'BUCT3': BASE + IDENTITY + ['-p', '57396', 'sbq@10sx4jr711576.vicp.fun']}


def deploy(item):
    name, target = item
    start = datetime.datetime.now(datetime.timezone.utc).isoformat()
    # All destinations are exclusive names within the previously verified root.
    command = f'''set -eu
set -C
cat > {ROOT}/reference_runtime.tar.zst.partial
actual=$(sha256sum {ROOT}/reference_runtime.tar.zst.partial)
test "${{actual%% *}}" = {SHA}
test ! -e {ROOT}/reference_runtime.tar.zst
mv -- {ROOT}/reference_runtime.tar.zst.partial {ROOT}/reference_runtime.tar.zst
mkdir {ROOT}/deployed
tar --zstd --no-same-owner -xf {ROOT}/reference_runtime.tar.zst -C {ROOT}/deployed
printf 'DEPLOYED {name} {SHA}\\n'
'''
    producer = subprocess.Popen(SOURCE + [f'cat {ROOT}/reference_runtime.tar.zst'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    consumer = subprocess.Popen(target + [command], stdin=producer.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    producer.stdout.close()
    output, error = consumer.communicate()
    source_error = producer.communicate()[1]
    receipt = {'host': name, 'start_utc': start, 'end_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'archive_sha256': SHA, 'source_rc': producer.returncode, 'target_rc': consumer.returncode, 'stdout': output.decode(errors='replace'), 'stderr': error.decode(errors='replace'), 'source_stderr': source_error.decode(errors='replace')}
    path = pathlib.Path(__file__).parent / f'deployment_{name}.json'
    with path.open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2)
    print(json.dumps(receipt), flush=True)
    return producer.returncode == consumer.returncode == 0


if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(2) as executor:
        results = list(executor.map(deploy, TARGETS.items()))
    raise SystemExit(0 if all(results) else 1)
