"""Run one recovered role's offline suite in an isolated interpreter and new artifact directory."""
import argparse
import json
import os
from pathlib import Path
import sys
import shlex

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("pair", type=Path)
parser.add_argument("role", choices=("mkm", "kmc"))
parser.add_argument("artifacts", type=Path)
parser.add_argument("ids", nargs="*")
args = parser.parse_args()
if not sys.flags.isolated or not sys.dont_write_bytecode:
    parser.error("Run with python -I -B")
pair = args.pair.resolve()
root = pair / args.role
out = args.artifacts.resolve()
if out.is_relative_to(pair) or out.is_relative_to(Path(__file__).resolve().parents[1]):
    parser.error("Choose an external artifact directory")
out.mkdir(parents=True, exist_ok=False)
os.environ.pop("PYTHONPATH", None)
for name in list(os.environ):
    if "NATIVE" in name.upper() or "LIVE_CATKINAS" in name.upper():
        os.environ.pop(name)
os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
for key in ("TEMP", "TMP", "TMPDIR"):
    os.environ[key] = str(out)
os.chdir(root)
sys.path[:0] = [str(root), str(root / "tests")]
originals = [Path(p) for p in json.loads((root / "evidence-mounts.json").read_bytes())]
accessed = set()


def guard(event, values):
    if event == "subprocess.Popen":
        command = values[1]
        first = shlex.split(command, posix=False)[0] if isinstance(command, str) else command[0]
        executable = Path(str(values[0] or first).strip('"')).stem.lower()
        if executable not in ("python", "python3", "git", "where"):
            raise RuntimeError(f"Offline verification forbids launching {executable}")
    if event == "open" and isinstance(values[0], (str, bytes, os.PathLike)):
        p = Path(os.fsdecode(values[0])).absolute()
        if any(p.is_relative_to(origin) for origin in originals):
            raise RuntimeError(f"Original installation access: {p}")
        if p.is_relative_to(pair):
            if values[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
                raise RuntimeError(f"Attempt to modify recovered input: {p}")
            accessed.add(p.relative_to(pair).as_posix())


sys.addaudithook(guard)
import pytest

modules = json.loads((Path(__file__).resolve().parent / "acceptance" / (args.role + "-modules.json")).read_bytes())
selection = args.ids or ["tests/" + name + ".py" for name in modules]
if not args.ids:
    selection.append("tests/test_v31_architecture.py")
    if args.role == "mkm":
        selection.extend(["tests/test_mkm_drc.py", "tests/test_kinetics_artifact_lifecycle.py",
                          "tests/test_execution_backends.py", "tests/test_aqcat25_handoff.py",
                          "tests/test_scientific_priority.py::test_immutable_human_review"])
code = pytest.main(["-q", "--tb=short", "-p", "no:cacheprovider", "--basetemp", str(out / "tmp"),
                    "--junitxml", str(out / "junit.xml"), *selection])
(out / "imports.json").write_text(json.dumps({k: v.__file__ for k, v in tuple(sys.modules.items())
    if (k == "scripts" or k.startswith("scripts.") or k == "sbq_kinetics_test_artifacts")
    and getattr(v, "__file__", None)}, indent=2), encoding="utf8")
(out / "reads.json").write_text(json.dumps(sorted(accessed)), encoding="utf8")
sys.exit(code)
