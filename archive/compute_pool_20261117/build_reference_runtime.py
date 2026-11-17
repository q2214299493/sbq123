"""Run on MZ73: package its existing Python environment without changing it."""
import hashlib
import json
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path('/home/sbq/sbq/compute_pool_20261117')
ROOT.mkdir(exist_ok=False)
stage = ROOT / 'stage'
runtime = stage / 'runtime'
(runtime / 'bin').mkdir(parents=True)
shutil.copy2('/usr/bin/python3.10', runtime / 'bin/python3.10')
stdlib = runtime / 'lib/python3.10'
stdlib.mkdir(parents=True)
for item in pathlib.Path('/usr/lib/python3.10').iterdir():
    (stdlib / item.name).symlink_to(item, target_is_directory=item.is_dir())
(stdlib / 'site-packages').symlink_to('/home/sbq/sbq/ml_ts_acceleration/venv/lib/python3.10/site-packages', target_is_directory=True)
(runtime / 'src').mkdir()
for name in ('arkimede', 'mlps_finetuning'):
    (runtime / 'src' / name).symlink_to('/home/sbq/sbq/ml_ts_acceleration/src/' + name, target_is_directory=True)
(runtime / 'extra').mkdir()
for name in ('python_pkgs', 'vendor'):
    (runtime / 'extra' / name).symlink_to('/home/sbq/sbq/aqcat25/' + name, target_is_directory=True)
launcher = runtime / 'python'
launcher.write_text('''#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
export PYTHONHOME="$root"
export PYTHONPATH="$root/src/arkimede:$root/src/mlps_finetuning:$root/extra/python_pkgs:$root/extra/vendor"
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
exec "$root/bin/python3.10" "$@"
''')
launcher.chmod(0o755)
models = stage / 'models'
models.mkdir()
checkpoint = pathlib.Path('/home/sbq/sbq/fe110_scratch512_20261028_v1/finetune/control/output/direct-fe110-scratch512-finetune20-20261028-v1/checkpoints/2026-10-28-20-56-32/best_checkpoint.pt')
checkpoint_sha = hashlib.file_digest(checkpoint.open('rb'), 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else hashlib.sha256(checkpoint.read_bytes()).hexdigest()
assert checkpoint_sha == 'cdd391d39ed19fc1ef3516d41b1af53bd81351d8ad73f25e537be232fd8c0dc0'
(models / 'aqcat25_ft512_development.pt').symlink_to(checkpoint)
(stage / 'provenance.json').write_text(json.dumps({'source_host': 'MZ73', 'source_python': '/usr/bin/python3.10', 'checkpoint_source': str(checkpoint), 'checkpoint_sha256': checkpoint_sha, 'model_status': 'unpromoted_development_checkpoint', 'scientific_job_authority': False}, indent=2) + '\n')
archive = ROOT / 'reference_runtime.tar.zst'
with archive.open('xb') as output:
    subprocess.run(['tar', '-h', '--exclude=__pycache__', '--exclude=*.pyc', '--exclude=.git', '-I', 'zstd -1 -T2', '-cf', '-', '-C', str(stage), '.'], stdout=output, check=True)
digest = hashlib.sha256()
with archive.open('rb') as handle:
    for chunk in iter(lambda: handle.read(8*1024*1024), b''):
        digest.update(chunk)
receipt = {'archive': str(archive), 'bytes': archive.stat().st_size, 'sha256': digest.hexdigest(), 'checkpoint_sha256': checkpoint_sha}
(ROOT / 'bundle_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt), flush=True)
