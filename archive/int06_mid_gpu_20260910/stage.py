"""Stage a new immutable GPU package and run a no-model remote preflight."""
import json
import shlex
import subprocess
import tarfile

from archive.int06_mid_gpu_20260910.inspect_remote import BASE
from archive.int06_mid_gpu_20260910.prepare import REMOTE
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive

SSH = ['ssh','-p','36039','-i','C:/Users/86177/.ssh/id_ed25519_fe_agent',
       '-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=15','sbq@10sx4jr711576.vicp.fun']
PYTHON = '/home/sbq/sbq/ml_ts_acceleration/venv/bin/python'


def invoke(code, name):
    result = subprocess.run([*SSH, PYTHON+' -'],input=code.encode(),capture_output=True,timeout=55)
    with (BASE/(name+'.stdout')).open('xb') as handle:
        handle.write(result.stdout)
    with (BASE/(name+'.stderr')).open('xb') as handle:
        handle.write(result.stderr)
    write_json_exclusive(BASE/(name+'.receipt.json'),{'exit_code':result.returncode})
    result.check_returncode()
    return result


def main():
    package = BASE/'payload'
    manifest = load_json_object(package/'payload_manifest.json')
    archive = BASE/'payload.tar'
    with tarfile.open(archive,'x') as handle:
        for relative in sorted(manifest['files'])+['payload_manifest.json']:
            handle.add(package/relative,arcname=relative,recursive=False)
    invoke('from pathlib import Path\np=Path('+repr(REMOTE)+')\n'
           'assert p.is_relative_to(Path("/home/sbq/sbq"))\np.mkdir(exist_ok=False)\nprint("new directory created")\n',
           'remote_stage_mkdir')
    scp = ['scp','-P','36039','-i','C:/Users/86177/.ssh/id_ed25519_fe_agent',
           '-o','IdentitiesOnly=yes','-o','BatchMode=yes',str(archive),
           'sbq@10sx4jr711576.vicp.fun:'+REMOTE+'/payload.tar']
    result = subprocess.run(scp,capture_output=True,text=True,timeout=55)
    write_json_exclusive(BASE/'scp_receipt.json',{'exit_code':result.returncode,'stderr':result.stderr,
                                                'archive_sha256':sha256_file(archive)})
    result.check_returncode()
    code = '''from pathlib import Path
import hashlib, subprocess, sys, tarfile
root=Path(ROOT_VALUE)
archive=root/'payload.tar'
h=hashlib.sha256()
with archive.open('rb') as handle:
 for block in iter(lambda:handle.read(1048576),b''): h.update(block)
assert h.hexdigest()==HASH_VALUE
with tarfile.open(archive) as handle:
 for item in handle.getmembers():
  assert item.isfile() and (root/item.name).resolve().is_relative_to(root)
  assert not (root/item.name).exists()
 handle.extractall(root)
for name in ['dual_model_ml_neb_job.sh','aqcat25_mz73_env.sh']:
 subprocess.run(['bash','-n',str(root/'runtime'/name)],check=True)
result=subprocess.run([sys.executable,'-B',str(root/'preflight.py')],check=True,capture_output=True,text=True)
print(result.stdout,end='')
'''.replace('ROOT_VALUE',repr(REMOTE)).replace('HASH_VALUE',repr(sha256_file(archive)))
    completed = invoke(code,'remote_preflight')
    preflight = json.loads(completed.stdout)
    assert preflight['status']=='PASS' and preflight['hostname']=='MZ73'
    assert preflight['request_sha256']==manifest['request_sha256']
    assert preflight['payload_manifest_sha256']==sha256_file(package/'payload_manifest.json')
    assert not preflight['model_execution_performed'] and not preflight['scheduler_submission_performed']
    write_json_exclusive(BASE/'remote_preflight.json',preflight)
    print(preflight)
    print('Staged at '+shlex.quote(REMOTE)+'; no model or scheduler execution')


if __name__ == '__main__':
    main()
