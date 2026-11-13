"""One compact read-only Slurm/VASP checkpoint; never accepts a force label."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import math
from pathlib import Path
import shlex
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.artifact_io import load_json_object, write_json_atomic, write_json_exclusive
from scripts.neb_agent.mz73_timebudget import NEXT_LEAF
from scripts.slurm_force_label import query_slurm_force_label

spec = importlib.util.spec_from_file_location('static_monitor_primary', Path(__file__).with_name('paper_training_job.py'))
primary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(primary)

REMOTE = '''import base64,json
from pathlib import Path
root=Path(__ROOT__)
r={}
for name in ('vasp.out','OSZICAR','OUTCAR','producer_exit_record.json'):
 p=root/name
 if p.is_file():
  size=p.stat().st_size
  with p.open('rb') as stream:
   stream.seek(max(0,size-12000));data=stream.read(12000)
  r[name]={'bytes':size,'tail_base64':base64.b64encode(data).decode()}
print(json.dumps(r))
'''


def electronic_rows(text):
    rows = []
    for line in text.splitlines(keepends=True):
        # A live write can stop before an exponent or the rest of a row.
        if not line.endswith('\n'):
            continue
        parts = line.split()
        if len(parts) >= 5 and parts[0] in ('DAV:', 'RMM:', 'CG:') and parts[1].isdigit():
            try:
                values = [float(token.replace('D', 'E')) for token in parts[2:5]]
                row = {'algorithm': parts[0][:-1], 'step': int(parts[1]),
                    **{key: value if math.isfinite(value) else None for key, value in zip(
                        ('energy_eV', 'delta_e_eV', 'delta_eps_eV'), values)}}
                if not all(math.isfinite(value) for value in values):
                    row['nonfinite_energy_values'] = True
                rows.append(row)
            except ValueError:
                continue
    return rows


def checkpoint(case, leaf=NEXT_LEAF):
    import base64

    directory = case / 'labels' / leaf
    record = load_json_object(directory / 'submission_record.json')
    primary.require(record['status'] == 'SUBMITTED', 'no known next DFT job')
    native = query_slurm_force_label(record['job_id'], record['remote_dir'], leaf)
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    destination = directory / 'monitor'
    destination.mkdir(exist_ok=True)
    write_json_exclusive(destination / ('slurm_' + timestamp + '.json'), native)
    if native['job_state'] in ('COMPLETED', 'FAILED', 'TIMEOUT', 'CANCELLED', 'NODE_FAIL', 'OUT_OF_MEMORY'):
        terminal = directory / ('slurm_' + record['job_id'] + '.terminal.json')
        if not terminal.exists():
            write_json_exclusive(terminal, native)
    backend = primary.remote.load_mz73_static_backend(leaf)
    program = REMOTE.replace('__ROOT__', repr(record['remote_dir']))
    result = primary.run(primary.remote.ssh_argv(backend, shlex.join(['python3', '-B', '-c', program])))
    packet = json.loads(result.stdout)
    tails = {name: base64.b64decode(value['tail_base64'], validate=True).decode(errors='replace') for name, value in packet.items()}
    stdout = electronic_rows(tails.get('vasp.out', ''))
    oszicar = electronic_rows(tails.get('OSZICAR', ''))
    ending = tails.get('OUTCAR', '')
    summary = {'job_id': record['job_id'], 'scheduler_state': native['job_state'], 'native_exit_code': native['exit_code'],
        'stdout_latest_electronic': stdout[-1] if stdout else None,
        'OSZICAR_latest_electronic': oszicar[-1] if oszicar else None,
        'OUTCAR_footer_seen': 'General timing and accounting' in ending,
        'file_sizes': {name: value['bytes'] for name, value in packet.items()},
        'force_label_accepted': False, 'scientific_TS_accepted': False,
        'electronic_convergence': 'requires owning final SCF parser', 'checked_at': native['checked_at']}
    write_json_atomic(directory / 'latest_monitor_checkpoint.json', {'summary': summary, 'raw_file_packet': packet})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-root', type=Path, required=True)
    parser.add_argument('--workdir-name', default=NEXT_LEAF)
    args = parser.parse_args()
    print(json.dumps(checkpoint(args.case_root.resolve(strict=True), args.workdir_name)))


if __name__ == '__main__':
    main()
