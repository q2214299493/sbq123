"""Check the three independent core wheels on one Python 3.13 CI runner."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import venv
import zipfile
from build import ROOT, build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    work = parser.parse_args().output.resolve()
    work.mkdir(parents=True, exist_ok=False)
    roles = ("common", "mkm", "kmc")
    wheels = {role: build(role, work / "wheels") for role in roles}
    for role in roles:
        build(role, work / "wheels")
    owners = set()
    for wheel in wheels.values():
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                if ".dist-info/" in name:
                    continue
                if name in owners or not name.startswith("sbq123/") or archive.read(name) != (ROOT / "src" / name).read_bytes():
                    raise ValueError("Invalid canonical wheel member: " + name)
                owners.add(name)
    historical = json.loads((ROOT / "v31/roles.json").read_bytes())
    variants = {n[4:] for n in historical if n.startswith("mkm/") and n.endswith(".py")
                and "kmc/" + n[4:] in historical and historical[n]["sha256"] != historical["kmc/" + n[4:]]["sha256"]}
    with (ROOT / "docs/v32/audit/role-variants.csv").open(encoding="utf8") as stream:
        inventory = {q["path"] for q in csv.DictReader(stream) if q["generation"] == "release" and q["path"].endswith(".py")}
    if len(variants) != 23 or variants != inventory:
        raise ValueError("V3.1 variant inventory changed")
    for role in roles:
        env = work / role
        venv.create(env)
        py = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        pip = [sys.executable, "-m", "pip", "--python", str(py)]
        def run(args):
            subprocess.run(args, check=True, cwd=work)
        run([py, "-I", "-c", "from importlib.util import find_spec; assert find_spec('sbq123') is None"])
        run([*pip, "install", "--no-compile", "--find-links", str(work / "wheels"), str(wheels[role])])
        run([*pip, "check"])
        run([py, "-I", "-B", ROOT / "tools/v32/check_install.py", role, ROOT, work / (role+".json")])
        if role == "common":
            run([*pip, "install", "--no-compile", "pytest==8.4.2"])
            run([py, "-I", "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-c",
                 ROOT / "packages/common/pyproject.toml", ROOT / "tests/v32/test_architecture_gate.py",
                 "--junitxml=" + str(work / "reliability.xml")])
    (work / "gate.json").write_text(json.dumps({"python": sys.version, "platform": sys.platform,
        "verified_variants": len(variants), "canonical_members": len(owners),
        "wheels": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in wheels.values()}}, indent=2), encoding="utf8")


if __name__ == "__main__":
    main()
