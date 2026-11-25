from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from scripts.convergence import setup_true_fe110_thickness_retest as campaign
from scripts.convergence import thickness_stage

ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which("bash") or ("C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else None)
COMPLETE = ("vasp.5.4.4\nIteration 1( 1)\naborting loop because EDIFF is reached\n"
            "free  energy   TOTEN  = -10.50000000 eV\nenergy(sigma->0) = -10.5\n"
            "General timing and accounting informations for this job:\n")

# The fake never executes the VASP argument it receives. It only creates synthetic
# files in the pytest case and returns a requested process code.
FAKE = r'''
import os, sys, json
from pathlib import Path
p=Path.cwd()
stage='relax' if p.name=='relax' else 'static'
with open(os.environ['FAKE_LOG'],'a') as handle: handle.write(stage+'\n')
mode=os.environ.get('FAKE_'+stage.upper(),'valid')
if os.environ.get('FAKE_RECEIPT_FAILURE'):
    root=p.parent if p.name in ['relax','static'] else p
    (root/'.thickness-attempt/result').mkdir(exist_ok=True)
if mode=='exit9': sys.exit(9)
if mode=='missing': sys.exit(0)
text=os.environ['FAKE_COMPLETE']
if stage=='relax': text=text.replace('General timing','reached required accuracy\nGeneral timing')
if mode=='noionic': text=text.replace('reached required accuracy','not ionically converged')
if mode=='nofooter': text=text.split('General timing')[0]
if mode=='noscf': text=text.replace('aborting loop because EDIFF is reached','electronic loop exhausted')
if mode=='truncated': text+='Iteration 2( '
if mode=='newcycle': text+='Iteration 2( 1)\n'
if mode=='newrun': text+='vasp.5.4.4 new run\n'
if mode=='fatal': text+='VERY BAD NEWS\n'
(p/'OUTCAR').write_text(text)
if stage=='relax':
    if mode!='no_contcar':
        data=(p/'POSCAR').read_bytes()
        if mode=='empty_contcar': data=b''
        if mode=='bad_contcar': data=b'not a structure'
        (p/'CONTCAR').write_bytes(data)
sys.exit(0)
'''


class Payload:
    def __init__(self, folder: Path, kind: str):
        if not BASH or not Path(BASH).is_file():
            if sys.platform.startswith('linux'):
                pytest.fail('Linux CI requires Bash for generated payload tests')
            pytest.skip('Bash not installed; Python tests still run')
        self.folder = folder
        self.output = folder / 'campaign'
        campaign.setup(self.output)
        self.kind = kind
        self.job = self.output / ('layers_4' if kind == 'chain' else 'bulk_reference')
        self.stages = [self.job / 'relax', self.job / 'static'] if kind == 'chain' else [self.job]
        for stage in self.stages:
            (stage / 'POTCAR').write_text('SYNTHETIC NON-POTENTIAL INPUT\n')
        self.script = self.job / ('run_chain.lsf' if kind == 'chain' else 'run.lsf')
        self.log = folder / 'fake_calls.log'
        writer = folder / 'fake_mpi.py'
        writer.write_text(FAKE, encoding='utf-8')
        env_script = folder / 'environment.sh'
        env_script.write_text('# initialization deliberately allows unset vendor variables\ntrue\n', newline='\n')
        mpi = folder / 'mpirun'
        mpi.write_text('#!/bin/bash\nexec "$FAKE_PYTHON" "$FAKE_WRITER"\n', newline='\n')
        mpi.chmod(0o700)
        vasp = folder / 'vasp_stub'
        vasp.write_text('#!/bin/bash\nexit 99\n', newline='\n')
        vasp.chmod(0o700)
        self.env = {**os.environ, 'THICKNESS_ENV_SCRIPT':env_script.as_posix(),
                    'THICKNESS_MPI':mpi.as_posix(), 'THICKNESS_VASP':vasp.as_posix(),
                    'THICKNESS_PYTHON':Path(sys.executable).as_posix(), 'FAKE_PYTHON':Path(sys.executable).as_posix(),
                    'FAKE_WRITER':writer.as_posix(), 'FAKE_LOG':self.log.as_posix(), 'FAKE_COMPLETE':COMPLETE,
                    'LSB_HOSTS':'synthetic-node synthetic-node', 'PYTHONPATH':str(ROOT), 'PYTHONUTF8':'1'}
        self.env.pop('BASH_ENV', None)
        self.env.pop('PYTHONHOME', None)

    def run(self):
        return subprocess.run([BASH, self.script.as_posix()], cwd=self.job, env=self.env,
                              capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=35)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def record(self):
        path = self.job / thickness_stage.ATTEMPT / 'result'
        return path.read_text() if path.exists() else 'UNKNOWN_NEEDS_REVIEW'


@pytest.mark.parametrize('kind', ['chain', 'static'])
def test_generated_payload_positive_and_reentry(tmp_path, kind):
    p = Payload(tmp_path, kind)
    assert p.script.read_text().startswith('#!/bin/bash\n')
    syntax = subprocess.run([BASH, '-n', p.script.as_posix()], capture_output=True)
    assert syntax.returncode == 0
    result = p.run()
    assert result.returncode == 0, result.stderr
    assert p.calls() == (['relax', 'static'] if kind == 'chain' else ['static'])
    assert 'COMPLETE stage=complete exit_code=0 scientific_acceptance=false' in p.record()
    if kind == 'chain':
        # A legitimately unchanged structure is not rejected as stale.
        assert (p.job/'static/POSCAR').read_bytes() == (p.job/'relax/CONTCAR').read_bytes()
    before = {f:f.read_bytes() for f in p.job.rglob('*') if f.is_file()}
    assert p.run().returncode != 0
    assert all(f.read_bytes() == data for f, data in before.items())


@pytest.mark.parametrize('kind', ['chain', 'static'])
@pytest.mark.parametrize('dependency', ['environment_missing', 'environment_fails', 'mpi', 'vasp', 'python', 'validator',
                                      'hosts', 'blank_hosts', 'invalid_hosts'])
def test_initialization_failure_never_calculates(tmp_path, kind, dependency):
    p = Payload(tmp_path, kind)
    if dependency == 'environment_fails':
        Path(p.env['THICKNESS_ENV_SCRIPT']).write_text('return 17\n')
    elif dependency == 'environment_missing':
        p.env['THICKNESS_ENV_SCRIPT'] = str(tmp_path/'missing')
    elif dependency == 'hosts':
        p.env['LSB_HOSTS'] = ''
    elif dependency == 'blank_hosts':
        p.env['LSB_HOSTS'] = '   '
    elif dependency == 'invalid_hosts':
        p.env['LSB_HOSTS'] = 'node;false'
    elif dependency == 'validator':
        p.env['PYTHONPATH'] = str(tmp_path/'no-package')
        # This interpreter is isolated from cwd/PYTHONPATH, with no repo package.
        wrapper = tmp_path/'python-without-package'
        wrapper.write_text('#!/bin/bash\nexec "$FAKE_PYTHON" -I -S "$@"\n', newline='\n')
        wrapper.chmod(0o700)
        p.env['THICKNESS_PYTHON'] = wrapper.as_posix()
    else:
        p.env['THICKNESS_'+dependency.upper()] = str(tmp_path/'missing')
    result = p.run()
    assert result.returncode != 0 and p.calls() == []
    assert 'FAILED' in p.record()
    if dependency == 'environment_fails':
        assert result.returncode == 17 and 'exit_code=17' in p.record()


@pytest.mark.parametrize('kind', ['chain', 'static'])
def test_old_evidence_rejected_before_overwrite(tmp_path, kind):
    p = Payload(tmp_path, kind)
    for stage in p.stages:
        (stage/'OUTCAR').write_text(COMPLETE+'reached required accuracy\n')
        (stage/'CONTCAR').write_text('OLD STRUCTURE\n')
        (stage/'vasp.out').write_text('OLD LOG\n')
    p.env.update(FAKE_RELAX='exit9', FAKE_STATIC='exit9')
    before = {f:f.read_bytes() for f in p.job.rglob('*') if f.is_file()}
    result = p.run()
    assert result.returncode != 0 and p.calls() == []
    assert all(f.read_bytes() == data for f, data in before.items())


def test_dirty_static_is_checked_before_relaxation(tmp_path):
    p = Payload(tmp_path, 'chain')
    (p.job/'static/OUTCAR').write_text(COMPLETE)
    assert p.run().returncode != 0 and p.calls() == []
    assert (p.job/'static/OUTCAR').read_text() == COMPLETE


@pytest.mark.parametrize('mode', ['exit9', 'missing', 'noionic', 'nofooter', 'noscf', 'truncated',
                                  'newcycle', 'newrun', 'fatal', 'no_contcar', 'empty_contcar', 'bad_contcar'])
def test_relaxation_failure_stops_handoff(tmp_path, mode):
    p = Payload(tmp_path, 'chain')
    before = (p.job/'static/POSCAR').read_bytes()
    p.env['FAKE_RELAX'] = mode
    result = p.run()
    assert result.returncode != 0, result.stderr
    assert p.calls() == ['relax']
    assert (p.job/'static/POSCAR').read_bytes() == before
    assert 'FAILED' in p.record()
    if mode == 'exit9':
        assert result.returncode == 9 and 'stage=relax exit_code=9' in p.record()


@pytest.mark.parametrize('kind', ['chain', 'static'])
@pytest.mark.parametrize('mode', ['exit9', 'missing', 'nofooter', 'noscf', 'truncated', 'newcycle', 'newrun', 'fatal'])
def test_static_failure_never_completes(tmp_path, kind, mode):
    p = Payload(tmp_path, kind)
    p.env['FAKE_STATIC'] = mode
    result = p.run()
    assert result.returncode != 0, result.stderr
    assert p.calls() == (['relax','static'] if kind == 'chain' else ['static'])
    assert 'FAILED' in p.record()
    if mode == 'exit9':
        assert result.returncode == 9


def test_payload_competition_has_one_owner(tmp_path):
    p = Payload(tmp_path, 'chain')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _:p.run(), range(2)))
    assert sorted(r.returncode for r in results) == [0,73]
    assert p.calls() == ['relax','static']


def test_payload_termination_stops_downstream(tmp_path):
    p = Payload(tmp_path, 'chain')
    Path(p.env['THICKNESS_MPI']).write_text('#!/bin/bash\nprintf "relax\\n" >> "$FAKE_LOG"\nkill -TERM "$PPID"\nexit 9\n', newline='\n')
    result = p.run()
    assert result.returncode == 143 and p.calls() == ['relax']
    assert 'FAILED' in p.record()


def test_atomic_handoff_failure_does_not_enter_static(tmp_path):
    p = Payload(tmp_path, 'chain')
    original = (p.job/'static/POSCAR').read_bytes()
    injection = tmp_path/'replace_failure.py'
    injection.write_text("""import os, runpy, sys
real = os.replace
def fail(source, target):
    if str(target).endswith('POSCAR'): raise OSError('injected atomic publish failure')
    return real(source, target)
os.replace = fail
sys.argv = sys.argv[2:]
runpy.run_module('scripts.convergence.thickness_stage', run_name='__main__')
""")
    wrapper = tmp_path/'python-fault'
    wrapper.write_text('#!/bin/bash\nexec "$FAKE_PYTHON" "$FAULT_SCRIPT" "$@"\n', newline='\n')
    wrapper.chmod(0o700)
    p.env.update(THICKNESS_PYTHON=wrapper.as_posix(), FAULT_SCRIPT=injection.as_posix())
    result = p.run()
    assert result.returncode != 0 and p.calls() == ['relax'], result.stderr
    assert (p.job/'static/POSCAR').read_bytes() == original
    assert not list((p.job/'static').glob('.POSCAR-handoff-*'))


@pytest.mark.parametrize('fault', ['machinefile', 'redirect', 'cd', 'input_disappears'])
def test_filesystem_failures_propagate_without_computation(tmp_path, fault):
    p = Payload(tmp_path, 'static' if fault == 'input_disappears' else 'chain')
    injection = tmp_path/'filesystem_fault.py'
    injection.write_text('''import os, runpy, sys
from pathlib import Path
sys.argv = sys.argv[2:]
args = sys.argv[1:]
try:
    runpy.run_module('scripts.convergence.thickness_stage', run_name='__main__')
except SystemExit as exc:
    if exc.code: raise
if '--root' in args:
    root=Path(args[args.index('--root')+1])
    if os.environ['FAULT'] == 'machinefile' and args[0] == 'preflight':
        (root/'nodelist').mkdir()
    if os.environ['FAULT'] == 'input_disappears' and args[0] == 'preflight':
        (root/'KPOINTS').unlink()
    if args[0] == 'inputs':
        if os.environ['FAULT'] == 'redirect': (root/'relax/vasp.out').mkdir()
        if os.environ['FAULT'] == 'cd': (root/'relax').rename(root/'relax-held')
''')
    wrapper = tmp_path/'python-filesystem-fault'
    wrapper.write_text('#!/bin/bash\nexec "$FAKE_PYTHON" "$FAULT_SCRIPT" "$@"\n', newline='\n')
    wrapper.chmod(0o700)
    p.env.update(THICKNESS_PYTHON=wrapper.as_posix(), FAULT_SCRIPT=injection.as_posix(), FAULT=fault)
    result = p.run()
    assert result.returncode != 0 and p.calls() == [], result.stderr
    assert 'FAILED' in p.record()


@pytest.mark.parametrize('mode,expected', [('valid',74), ('exit9',9)])
def test_receipt_failure_cannot_mask_process_failure_or_report_success(tmp_path, mode, expected):
    p = Payload(tmp_path, 'static')
    p.env.update(FAKE_RECEIPT_FAILURE='1', FAKE_STATIC=mode)
    result = p.run()
    assert result.returncode == expected
    assert not (p.job/thickness_stage.ATTEMPT/'result').is_file()


@pytest.mark.parametrize('name', ['OUTCAR', 'CONTCAR', '.thickness-attempt', 'submission_attempt.json'])
def test_setup_refuses_entire_campaign_before_any_write(tmp_path, name):
    campaign.setup(tmp_path)
    location = tmp_path/'bulk_reference'/name
    location.write_text('prior evidence')
    before = {p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    with pytest.raises(ValueError, match='existing execution evidence'):
        campaign.setup(tmp_path)
    assert all(p.read_bytes() == value for p,value in before.items())


def test_input_only_setup_is_repeatable(tmp_path):
    campaign.setup(tmp_path)
    before = {p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    campaign.setup(tmp_path)
    assert all(p.read_bytes() == value for p,value in before.items())


def test_symlink_escape_rejected(tmp_path):
    campaign.setup(tmp_path/'campaign')
    outside = tmp_path/'outside'
    outside.write_text('outside')
    target = tmp_path/'campaign/layers_4/relax/OUTCAR'
    try:
        target.symlink_to(outside)
    except OSError:
        pytest.skip('OS does not permit unprivileged symlinks')
    with pytest.raises(ValueError, match='escapes|symlink'):
        campaign.setup(tmp_path/'campaign')
    assert outside.read_text() == 'outside'


def test_payload_rejects_stage_symlink(tmp_path):
    p = Payload(tmp_path, 'chain')
    stage = p.job/'static'
    outside = tmp_path/'static-outside'
    stage.rename(outside)
    try:
        stage.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip('OS does not permit unprivileged symlinks')
    before = {f:f.read_bytes() for f in outside.iterdir() if f.is_file()}
    assert p.run().returncode != 0 and p.calls() == []
    assert all(f.read_bytes() == value for f,value in before.items())


def test_summary_uses_real_structures_formula_and_current_state(tmp_path):
    campaign.setup(tmp_path)
    (tmp_path/'bulk_reference/OUTCAR').write_text(COMPLETE.replace('-10.50000000', '-10.0'))
    for layers in campaign.LAYERS:
        total = -5 * 9 * layers + 2.0
        (tmp_path/f'layers_{layers}/static/OUTCAR').write_text(COMPLETE.replace('-10.50000000', str(total)))
    campaign.summarize(tmp_path)
    rows = json.loads((tmp_path/'thickness_summary.json').read_text())
    for row in rows:
        atoms = campaign.read(tmp_path/f"layers_{row['layers']}/static/POSCAR")
        area = float(campaign.np.linalg.norm(campaign.np.cross(atoms.cell[0], atoms.cell[1])))
        assert row['surface_excess_J_m2'] == pytest.approx(2.0/(2*area)*campaign.EV_A2_TO_J_M2)
        assert row['output_status'] == 'COMPLETE' and row['scientific_acceptance'] is False
    path = tmp_path/'layers_4/static/OUTCAR'
    path.write_text(COMPLETE+'Iteration 2( 1)\n')
    (tmp_path/'layers_5/static/OUTCAR').unlink()
    campaign.summarize(tmp_path)
    rows = json.loads((tmp_path/'thickness_summary.json').read_text())
    assert rows[0]['surface_excess_J_m2'] is None and rows[0]['output_status'] == 'INCOMPLETE_OR_FAILED'
    assert rows[1]['static_toten_eV'] is None and rows[1]['surface_excess_J_m2'] is None


@pytest.mark.parametrize('text', ['', 'free energy TOTEN = NaN eV\n', COMPLETE+'Iteration 2( '])
def test_summary_rejects_invalid_bulk(tmp_path, text):
    campaign.setup(tmp_path)
    (tmp_path/'bulk_reference/OUTCAR').write_text(text)
    with pytest.raises((ValueError, RuntimeError)):
        campaign.summarize(tmp_path)
    assert not (tmp_path/'thickness_summary.json').exists()


def test_summary_missing_bulk_and_invalid_slab_preserve_existing_report(tmp_path):
    campaign.setup(tmp_path)
    summary = tmp_path/'thickness_summary.json'
    summary.write_text('previous report')
    with pytest.raises(RuntimeError, match='no TOTEN'):
        campaign.summarize(tmp_path)
    (tmp_path/'bulk_reference/OUTCAR').write_text(COMPLETE)
    (tmp_path/'layers_4/static/OUTCAR').write_text(COMPLETE+'free energy TOTEN = Inf eV\n')
    with pytest.raises(ValueError, match='finite'):
        campaign.summarize(tmp_path)
    assert summary.read_text() == 'previous report'
