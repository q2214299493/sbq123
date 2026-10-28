"""Compact read-only sequence checkpoint;no model or calculation is started."""
import base64
import json
import shlex

from .prepare import REMOTE
from .probe import OUTPUT, PYTHON
from .transport import call

PROGRAM = r'''import json,os,re
from pathlib import Path
root=Path(ROOT);result={'records':{},'controller_alive':False}
names=['sequence_launch_receipt.json','sequence_exit.json','nequip_started.json','nequip_stage_exit.json',
 'nequip_v2/output/model_device.json','nequip_v2/producer_exit_record.json','finetune/direct_launch_receipt.json',
 'finetune/direct_started.json','finetune/direct_batch_exit_record.json',
 'finetune/control/output/direct-fe110-scratch512-finetune20-20261028-v1/native_two_backward_check.json',
 'finetune/control/output/direct-fe110-scratch512-finetune20-20261028-v1/training_completed.json',
 'finetune/control/output/direct-fe110-scratch512-finetune20-20261028-v1/execution_device.json']
for name in names:
 p=root/name
 if p.is_file():
  if p.stat().st_size>1024**2:raise ValueError('receipt exceeds cap')
  result['records'][name]=json.loads(p.read_bytes())
launch=result['records'].get('sequence_launch_receipt.json')
if launch:
 p=Path('/proc')/str(launch['pid'])/'cmdline'
 if p.exists():result['controller_alive']=launch['request_sha256'].encode() in p.read_bytes()
for rel in ['nequip_controller.log','nequip_v2/training.log','finetune/control/output/direct-fe110-scratch512-finetune20-20261028-v1/training.log']:
 p=root/rel
 if p.is_file():
  with p.open('rb') as f:f.seek(max(0,p.stat().st_size-6000));tail=f.read().decode(errors='replace')
  if 'Traceback' in tail:result.setdefault('error_tails',{})[rel]=tail[-2800:]
  steps=re.findall(r'step:s*([0-9.eE+-]+)',tail)
  if steps:result['latest_logged_FT_iteration_rounded']=int(float(steps[-1]))
print(json.dumps(result),flush=True)
'''


def status(name):
    program = "ROOT=" + repr(REMOTE) + "\n" + PROGRAM
    code = "exec(__import__('base64').b64decode('" + base64.b64encode(program.encode()).decode() + "'))"
    result = json.loads(call(shlex.join([PYTHON, "-c", code]), name))
    from scripts.artifact_io import write_json_exclusive
    write_json_exclusive(OUTPUT / (name + ".json"), result)
    print(result)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    status(parser.parse_args().snapshot)
