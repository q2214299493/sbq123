"""Run a fresh installed-role check. Used by both OSes in the GitHub Actions matrix."""

import argparse
import os
from pathlib import Path
import subprocess
import venv

from build import build, DISTS, ROOT


def run(cmd, work, env=None):
    subprocess.run([str(s) for s in cmd], check=True, cwd=work, env=env)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("role", choices=[*DISTS, "reactor-dynamic"])
    p.add_argument("work", type=Path)
    args = p.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    wheels = {role: build(role, work / "wheels") for role in DISTS}
    for role in DISTS:
        build(role, work / "wheels")
    env = work / "env"
    venv.create(env, with_pip=True)
    py = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    role = "reactor" if args.role == "reactor-dynamic" else args.role
    specification = {"reactor-dynamic": "sbq123-reactor-cantera[dynamic]==3.2.0"}.get(args.role, str(wheels[role]))
    run([py, "-m", "pip", "install", "--find-links", work / "wheels", specification], work)
    run([py, "-m", "pip", "check"], work)
    run([py, "-I", "-B", ROOT / "tools/v32/check_install.py", args.role, ROOT, work / "installed.json"], work)
    if args.role in ("mkm", "kmc", "reactor-dynamic"):
        run([py, "-m", "pip", "install", "-r", ROOT / "v31/requirements.lock"], work)
    if args.role == "reactor-dynamic":
        run(
            [
                py,
                "-I",
                "-B",
                "-m",
                "pytest",
                "-q",
                "-c",
                ROOT / "packages/reactor/pyproject.toml",
                ROOT / "tests/v32",
                "--junitxml=" + str(work / "reactor.xml"),
            ],
            work,
        )
    if args.role in ("mkm", "kmc"):
        for role in ("mkm", "kmc"):
            run([py, "-I", "-B", ROOT / "tools/v32/prepare_history.py", ROOT / "v31", role, work / "fixtures" / role], work)
        context = dict(os.environ)
        if args.role == "kmc":
            mk = work / "mkm-env"
            venv.create(mk, with_pip=True)
            worker = mk / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            run([worker, "-m", "pip", "install", "-r", ROOT / "v31/requirements.lock"], work)
            run([worker, "-m", "pip", "install", "--no-index", "--no-deps", wheels["common"], wheels["mkm"]], work)
            context["SBQ123_MKM_PYTHON"] = str(worker)
        run(
            [
                py,
                "-I",
                "-B",
                ROOT / "tools/v32/regression.py",
                args.role,
                work / "fixtures" / args.role,
                ROOT / "v31/acceptance",
                work / "history",
            ],
            work,
            context,
        )


if __name__ == "__main__":
    main()
