"""Stage only this retry's changes;preserve unrelated dirty working-tree content."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def git(*args, data=None):
    result = subprocess.run(["git", *args], cwd=ROOT, input=data, capture_output=True, check=True)
    return result.stdout


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def head(path):
    return git("show", "HEAD:" + path).decode("utf-8")


def stage_blob(path, content):
    sha = git("hash-object", "-w", "--stdin", data=content.encode("utf-8")).decode().strip()
    git("update-index", "--add", "--cacheinfo", "100644," + sha + "," + path)


def main():
    if git("diff", "--cached", "--name-only").strip():
        raise RuntimeError("preserve already-staged changes")
    path = "configs/execution_backends.yaml"
    current = text(path)
    start = current.index("      fe110_adsorption_role_training_retry_20261020:")
    end = current.index("      fe110_adsorption_role_training_20261020:", start)
    anchor = "    direct_execution_exceptions:\n"
    stage_blob(path, head(path).replace(anchor, anchor + current[start:end], 1))

    path = "modules/adsorption_workflow/README.md"
    current = text(path)
    start = current.index("The separately authorized corrected attempt is recorded in")
    end = current.index("### Authorized MatRIS adsorption trial", start)
    stage_blob(path, head(path).replace("### Authorized MatRIS adsorption trial", current[start:end] + "### Authorized MatRIS adsorption trial", 1))

    path = "tasks/backlog.md"
    marker = "## Retained during adsorption model calibration (2026-10-18)"
    end_marker = "<!-- state-handoff:start task_backlog_events -->"
    before, current = head(path), text(path)
    stage_blob(path, before[:before.index(marker)] + current[current.index(marker):current.index(end_marker)] + before[before.index(end_marker):])

    path = "docs/04_ERROR_LOG.md"
    before, current = head(path), text(path)
    lines = before.splitlines(keepends=True)
    replacement = next(line for line in current.splitlines(keepends=True) if line.startswith("| `E-ADS-2185-06C`"))
    stage_blob(path, "".join(replacement if line.startswith("| `E-ADS-2185-06C`") else line for line in lines if not line.startswith("| `E-ADS-ROLE-DDP-20261020`")))

    path = "docs/05_FILE_INDEX.md"
    marker = "## Corrected adsorption training retry (2026-10-20)"
    stage_blob(path, head(path).rstrip() + "\n\n" + text(path)[text(path).index(marker):])

    path = "tasks/current_task.md"
    pattern = r"<!-- state-handoff:start current_task -->.*?<!-- state-handoff:end current_task -->"
    unit = re.search(pattern, text(path), flags=re.S).group()
    stage_blob(path, re.sub(pattern, lambda _: unit, head(path), flags=re.S))

    path = "data/state_handoff/projection_manifest.json"
    pattern = r'    "tasks/current_task.md#current_task": \{\n.*?\n    \}'
    unit = re.search(pattern, text(path), flags=re.S).group()
    stage_blob(path, re.sub(pattern, lambda _: unit, head(path), count=1, flags=re.S))

    paths = ["scripts/adsorption/direct_force_training.py", "scripts/adsorption/direct_training_arm.py",
        "scripts/adsorption/force_training_preflight.py", "docs/reviews/fe110_adsorption_training_retry_20261020.md",
        "modules/state_handoff/events/task-fe110-adsorption-corrected-training-completed-20261020.json"]
    paths += [p.relative_to(ROOT).as_posix() for p in Path(__file__).parent.iterdir() if p.suffix in (".py", ".md")]
    git("add", "-f", "--", *paths)
    git("diff", "--cached", "--check")
    print(git("diff", "--cached", "--stat").decode())


if __name__ == "__main__":
    main()
