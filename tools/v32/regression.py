"""Replay historical pytest cases against one installed V3.2 role (no native engines)."""

import argparse
import json
import os
from pathlib import Path
import shlex
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("role", choices=["mkm", "kmc"])
    p.add_argument("data", type=Path)
    p.add_argument("catalog", type=Path, help="The immutable v31/acceptance directory")
    p.add_argument("output", type=Path)
    args = p.parse_args()
    if not sys.flags.isolated:
        raise RuntimeError("Use python -I")
    root = args.data.resolve()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    from sbq123.common.artifacts.legacy_views import launchers

    expected = launchers(args.role)
    for path in (root / "scripts").rglob("*.py"):
        if expected.get(path.relative_to(root).as_posix()) != path.read_bytes():
            raise RuntimeError("Unexpected Python in data-only fixture")
    for n in list(os.environ):
        if "NATIVE" in n.upper() or "LIVE_CATKINAS" in n.upper():
            os.environ.pop(n)
    os.environ.update(SBQ123_ROLE_DATA=str(root), PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONDONTWRITEBYTECODE="1")
    from sbq123.common.compat import activate

    activate(args.role)
    os.chdir(root)
    sys.path[:0] = [str(root), str(root / "tests")]

    def audit(event, values):
        if event == "subprocess.Popen":
            command = values[1]
            executable = values[0] or (shlex.split(command, posix=False)[0] if isinstance(command, str) else command[0])
            if Path(str(executable).strip('"')).stem.lower() not in ("python", "python3", "git", "where"):
                raise RuntimeError("External engine execution disabled during offline regression")

    sys.addaudithook(audit)
    import pytest

    class HistoricalNegativeFixture:
        @pytest.fixture(autouse=True)
        def legacy_invalid_claim(self, request, monkeypatch):
            # This original negative case must reach the verifier with a deliberately
            # malformed V3.1 wire document. V3.2's writer rejects it even earlier.
            if request.node.name == "test_launch_timeout_is_bounded" and os.name == "nt":
                # This frozen unit test provides a wait-only fake PID. Adapt the
                # OS boundary, keeping launch(), run_bounded() and both deadlines.
                import subprocess
                from types import SimpleNamespace
                from sbq123.common.workflow import _windows_job, process

                class SimulatedJob:
                    def start(self, command, kwargs):
                        self.child = subprocess.Popen(command, **kwargs)
                        return SimpleNamespace(communicate=self.child.wait)

                    def terminate(self):
                        self.child.kill()

                    def close(self):
                        pass

                monkeypatch.setattr(_windows_job, "WindowsJob", SimulatedJob)
                monkeypatch.setattr(process, "time", SimpleNamespace(monotonic=lambda: 0.0))
            if request.node.name == "test_explicit_alternate_is_scoped_and_keeps_default":
                # Pre-bind the one historical operator-reviewed test configuration
                # before the test writes its file. Production receives no new pin.
                import hashlib
                import yaml
                from scripts.execution_backends import DEFAULT_CONFIG

                expected = yaml.safe_load(DEFAULT_CONFIG.read_bytes())
                expected["backends"]["vasp"]["authorized_alternates"] = {
                    "reviewed-temp": {"scheduler": "LSF", "scope": "reviewed-job"}
                }
                raw = yaml.safe_dump(expected).replace("\n", os.linesep).encode()
                monkeypatch.setenv("SBQ123_APPROVED_BACKEND_SHA256", hashlib.sha256(raw).hexdigest())
            if request.node.name == "test_geometry_alias_types_at_public_boundaries[pattern-nan]":
                import hashlib

                def legacy_hash_for_test(proposal):
                    body = {k: v for k, v in proposal.items() if k != "proposal_id"}
                    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=True).encode()
                    proposal["proposal_id"] = hashlib.sha256(raw).hexdigest()

                monkeypatch.setattr(request.module, "_rehash", legacy_hash_for_test)

    selection = ["tests/" + n + ".py" for n in json.loads((args.catalog / (args.role + "-modules.json")).read_bytes())]
    selection.extend(["tests/test_v31_architecture.py", "tests/test_v31_closure.py"])
    if args.role == "mkm":
        selection.extend(
            [
                "tests/test_mkm_drc.py",
                "tests/test_kinetics_artifact_lifecycle.py",
                "tests/test_execution_backends.py",
                "tests/test_aqcat25_handoff.py",
                "tests/test_scientific_priority.py::test_immutable_human_review",
            ]
        )
    selection = [s for s in selection if not s.startswith("tests/test_scientific_priority.py")]
    selection.append("tests/test_scientific_priority.py")
    code = pytest.main(
        [
            "-q",
            "--continue-on-collection-errors",
            "--tb=short",
            "-p",
            "no:cacheprovider",
            "--basetemp",
            str(out / "tmp"),
            "--junitxml",
            str(out / "junit.xml"),
            *selection,
        ],
        plugins=[HistoricalNegativeFixture()],
    )
    origins = {k: m.__file__ for k, m in sys.modules.items() if k.startswith("scripts.") and getattr(m, "__file__", None)}
    (out / "imports.json").write_text(json.dumps(origins, indent=2), encoding="utf8")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
