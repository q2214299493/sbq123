from __future__ import annotations

import ast
from pathlib import Path

import pytest

from scheduler_architecture import MUTATION, dispatch_sites


ROOT = Path(__file__).resolve().parents[1]
OWNER = "scripts/neb_agent/submission.py"


@pytest.mark.parametrize("source", [
    'import subprocess; subprocess.run(["bsub", "run.lsf"])',
    'import subprocess as sp; sp.Popen(["sbatch", "job.sh"])',
    'from subprocess import run as execute; execute(["qdel", job])',
    'import os; os.system("bkill 123")',
    'import os as system; system.popen("scancel 123")',
    'import subprocess; subprocess.run("qsub job.sh", shell=True)',
    'import subprocess; cmd = ["ssh", host, "bash -lc \'bsub run.lsf\'"]; subprocess.run(cmd)',
    'import subprocess\ndef launch(argv):\n return subprocess.Popen(argv)\ncommand="bsub job.lsf"\nlaunch(["ssh", host, command])',
    'import subprocess\ncommand="cd job"\ncommand += " && bsub job.lsf"\nsubprocess.run(command, shell=True)',
    'import subprocess\ncommand=["ssh", host]\ncommand.append("bkill 123")\nsubprocess.run(command)',
    'import subprocess\ndef command():\n return ["qsub", "job.sh"]\nsubprocess.run(command())',
    'import subprocess; subprocess.Popen(["bs" + "ub", "job.lsf"])',
])
def test_semantic_guard_rejects_alternative_dispatch_forms(source):
    assert dispatch_sites(ast.parse(source))


@pytest.mark.parametrize("source", [
    'import subprocess; subprocess.run(["ssh", host, "bjobs", "-a", job])',
    'template = "bsub script.lsf"',
    'def explain():\n """Never bsub here."""\n return "review required"',
    'import subprocess; subprocess.run(["python", "--help"])',
])
def test_semantic_guard_allows_queries_and_inert_templates(source):
    assert dispatch_sites(ast.parse(source)) == []


def test_all_maintained_scheduler_mutations_have_one_owner():
    owners = set()
    for directory in ("scripts", "modules", "skills"):
        for path in (ROOT / directory).rglob("*.py"):
            if "archive" in path.parts or "__pycache__" in path.parts:
                continue
            if dispatch_sites(ast.parse(path.read_text(encoding="utf-8-sig"))):
                owners.add(path.relative_to(ROOT).as_posix())
    assert owners == {OWNER}


def test_maintained_shells_do_not_own_scheduler_mutation():
    for directory in ("scripts", "modules", "skills"):
        for path in (ROOT / directory).rglob("*"):
            if path.suffix not in {".sh", ".ps1", ".bat", ".cmd"} or "archive" in path.parts or "templates" in path.parts:
                continue
            lines = path.read_text(encoding="utf-8-sig").splitlines()
            assert not any(MUTATION.search(line) for line in lines if not line.lstrip().startswith("#")), path
