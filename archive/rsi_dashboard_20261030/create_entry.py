"""One-off local entry creation; never starts models, jobs, or browser UI here."""
from pathlib import Path
import shutil
import sys

REPO = Path(__file__).resolve().parents[2]
ROOT = Path(r"C:\Users\86177\Desktop\fe110_rsi_experiments\rsi_usage_dashboard_20261030")
RUNS = ROOT.parent / "rsi_runtime_policy_20261030/runs"
PROFILE = ROOT.parent / "rsi_runtime_policy_20261030/daily_profile.json"


def ps(value):
    return "'" + str(value).replace("'", "''") + "'"


def main():
    script = '''# Refresh/open only. Does not invoke run/resume, model authentication or scientific jobs.
[CmdletBinding()]
param([switch]$NoOpen, [string]$RunDirectory, [string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$rsiDashboardArgs = @('-X', 'utf8', '-m', 'scripts.research_assistant.cli', 'dashboard')
if ($RunDirectory) { $rsiDashboardArgs += @('--run', $RunDirectory) }
else { $rsiDashboardArgs += @('--runs-root', RUNS_VALUE) }
if ($OutputDirectory) { $rsiDashboardArgs += @('--output-dir', $OutputDirectory) }
if (-not $NoOpen) { $rsiDashboardArgs += '--open' }
Push-Location -LiteralPath REPO_VALUE
try {
    & PYTHON_VALUE @rsiDashboardArgs
    if ($LASTEXITCODE -ne 0) { throw "Dashboard generation exited $LASTEXITCODE" }
} finally { Pop-Location }
'''.replace('RUNS_VALUE', ps(RUNS)).replace('REPO_VALUE', ps(REPO)).replace('PYTHON_VALUE', ps(sys.executable))
    with (ROOT / 'Open-RSIDashboard.ps1').open('x', encoding='utf-8-sig') as handle:
        handle.write(script)
    wrapper = '''"""This task's research entry, including dashboard. Existing wrappers are preserved."""
from pathlib import Path
import sys
sys.path.insert(0, REPO_VALUE)
from scripts.research_assistant.cli import main

if __name__ == "__main__":
    arguments = sys.argv[1:]
    commands = {"run", "resume", "tools", "feedback", "spc-export", "policies", "usage", "dashboard"}
    command = arguments.pop(0) if arguments and arguments[0] in commands else "run"
    profile = ["--profile", PROFILE_VALUE] if command in {"run", "resume"} and "--profile" not in arguments else []
    sys.argv = [sys.argv[0], command, *profile, *arguments]
    main()
'''.replace('REPO_VALUE', repr(str(REPO))).replace('PROFILE_VALUE', repr(str(PROFILE)))
    with (ROOT / 'use_research.py').open('x', encoding='utf-8') as handle:
        handle.write(wrapper)
    shutil.copyfile(__file__, ROOT / 'create_entry.py')
    print({'powershell_entry': str(ROOT / 'Open-RSIDashboard.ps1'), 'research_entry': str(ROOT / 'use_research.py'),
           'python': sys.executable, 'default_profile': str(PROFILE)})


if __name__ == '__main__':
    main()
