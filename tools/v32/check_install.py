"""Verify the installed distribution in an isolated interpreter outside the repository."""

import argparse
import base64
import hashlib
from importlib import metadata, util
import json
from pathlib import Path
import subprocess
import sys
import sysconfig


def check(role, checkout):
    if not sys.flags.isolated:
        raise ValueError("Run this check with python -I")
    allowed = {"common": ("common",), "reactor": ("common", "reactor"), "mkm": ("common", "mkm"), "kmc": ("common", "kmc")}[role]
    if util.find_spec("scripts") is not None:
        raise RuntimeError("Root-level scripts was installed")
    result = {}
    seen = set()
    for owner in ("common", "mkm", "kmc", "reactor"):
        spec = util.find_spec("sbq123." + owner)
        if (owner in allowed) != (spec is not None):
            raise RuntimeError("Incorrect installation closure: " + owner)
        if owner not in allowed:
            continue
        dist = metadata.distribution("sbq123-reactor-cantera" if owner == "reactor" else "sbq123-" + owner)
        verified = 0
        for f in dist.files:
            if f.hash is None:
                continue
            p = Path(f.locate()).resolve()
            if p in seen:
                raise RuntimeError("Distribution file collision: " + str(p))
            seen.add(p)
            sha = base64.urlsafe_b64encode(hashlib.sha256(p.read_bytes()).digest()).decode().rstrip("=")
            if sha != f.hash.value:
                raise RuntimeError("Installed hash mismatch: " + str(f))
            verified += 1
        result[owner] = {"version": dist.version, "files": verified}
    if (util.find_spec("cantera") is not None) != (role == "reactor"):
        raise RuntimeError("Cantera optional dependency isolation failed")
    if role in ("mkm", "kmc"):
        from sbq123.common.compat import activate, historical_module
        import csv

        modules = []
        with (checkout / "docs/architecture/MODULE_RESPONSIBILITIES.csv").open(encoding="utf-8-sig") as stream:
            for row in csv.DictReader(stream):
                if role not in row["roles"].split(","):
                    continue
                n = row["entry_path"].removesuffix(".py").replace("/", ".")
                mod = historical_module(role, n)
                p = Path(mod.__file__).resolve()
                if not p.is_relative_to(Path(sysconfig.get_path("purelib")).resolve()):
                    raise RuntimeError("Foreign import " + str(p))
                modules.append(n)
        try:
            activate("kmc" if role == "mkm" else "mkm")
        except ValueError:
            pass
        else:
            raise RuntimeError("Foreign role accepted")
        points = []
        for ep in metadata.distribution("sbq123-" + role).entry_points:
            if ep.group != "console_scripts":
                continue
            if not callable(ep.load()):
                raise RuntimeError(ep.name)
            cmd = Path(sysconfig.get_path("scripts")) / (ep.name + (".exe" if sys.platform == "win32" else ""))
            subprocess.run([cmd, "--help"], capture_output=True, check=True, timeout=45)
            points.append(ep.name)
        if len(points) != 9:
            raise RuntimeError("Incomplete role console entry inventory")
        result.update(architecture_imports=modules, console_scripts=points)
    if role == "reactor":
        from sbq123.reactor import simulate

        options = dict(
            kind="PFR",
            dataset_id="first-order",
            mode="fixed",
            temperature_K=400.0,
            pressure_Pa=400 * 8.31446261815324,
            composition={"A": 1.0, "B": 0.0},
            volume_m3=1.0,
            area_m2=1.0, inlet_mol_s=1.0,
            reactant="A",
            product="B",
        )
        out = simulate(**options)
        result["standalone_fixed_conversion"] = out["points"][-1]["conversion"]
        executable = Path(sysconfig.get_path("scripts")) / ("sbq123-reactor.exe" if sys.platform == "win32" else "sbq123-reactor")
        subprocess.run([executable, "--help"], check=True, capture_output=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=["mkm", "kmc", "common", "reactor"])
    parser.add_argument("checkout", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(check(args.role, args.checkout), indent=2) + "\n", encoding="utf8")
