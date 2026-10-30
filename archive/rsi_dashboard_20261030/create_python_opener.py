"""Add a Python-only opener; no execution-policy changes or browser launch here."""
from pathlib import Path
import shutil

REPO = Path(__file__).resolve().parents[2]
ROOT = Path(r"C:\Users\86177\Desktop\fe110_rsi_experiments\rsi_usage_dashboard_20261030")
RUNS = ROOT.parent / "rsi_runtime_policy_20261030/runs"


def main():
    source = '''"""Refresh and open only the local RSI dashboard; --no-open verifies generation."""
import sys
sys.path.insert(0, REPO_VALUE)
from scripts.research_assistant.cli import main

if __name__ == "__main__":
    arguments = sys.argv[1:]
    open_page = "--no-open" not in arguments
    arguments = [v for v in arguments if v != "--no-open"]
    sys.argv = [sys.argv[0], "dashboard", "--runs-root", RUNS_VALUE, *arguments, *(["--open"] if open_page else [])]
    main()
'''.replace('REPO_VALUE', repr(str(REPO))).replace('RUNS_VALUE', repr(str(RUNS)))
    with (ROOT / 'open_rsi_dashboard.py').open('x', encoding='utf-8') as handle:
        handle.write(source)
    shutil.copyfile(__file__, ROOT / 'create_python_opener.py')
    print(str(ROOT / 'open_rsi_dashboard.py'))


if __name__ == '__main__':
    main()
