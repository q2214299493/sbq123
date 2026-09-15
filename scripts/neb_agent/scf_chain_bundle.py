"""Build/verify the exact portable SCF runtime; never submit or authorize it."""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

from scripts.artifact_io import sha256_file
from scripts.neb_agent.scf_repair_chain import INPUTS, precheck

ROOT = Path(__file__).resolve().parents[2]
SOURCES = (
    "scripts/artifact_io.py", "scripts/scientific_validation.py", "scripts/vasp_result_gate.py",
    "scripts/neb_agent/utils_vasp.py", "scripts/neb_agent/scf_chain_evidence.py",
    "scripts/neb_agent/scf_repair_chain.py", "scripts/ts_strategy_engine/scf_chain_gate.py",
)
PACKAGES = ("scripts/__init__.py", "scripts/neb_agent/__init__.py", "scripts/ts_strategy_engine/__init__.py")
ENTRY = b"from scripts.neb_agent.scf_repair_chain import main\nraise SystemExit(main())\n"


def runtime_contents() -> dict[str, bytes]:
    return {**{name: (ROOT / name).read_bytes() for name in SOURCES},
            **{name: b"" for name in PACKAGES}, "__main__.py": ENTRY}


def build_runtime(output: Path) -> None:
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in runtime_contents().items():
            archive.writestr(zipfile.ZipInfo(name, date_time=(2026, 9, 15, 0, 0, 0)), data)


def launcher(ranks: int) -> str:
    # The exact site launcher is reviewed together with the bundle, not a shell
    # template accepting arbitrary user strings/commands.
    return f"""#!/bin/bash
#BSUB -R 'select[hname!=gknew0440]'
APP_NAME=Gkn_normal
NP={ranks}
NP_PER_NODE=32
RUN=RAW
set -e
export OMP_NUM_THREADS=1
source /home_gkx/env/intel/intel2016.sh
: "${{SCF_CHAIN_PERMIT:?canonical gate permit required}}"
exec python3 scf_chain_runtime.pyz
"""


def check_bundle(workdir: Path, cores: int | None) -> dict:
    manifest = precheck(workdir)
    ranks = manifest["runtime"]["ranks"]
    if cores != ranks or (workdir / "script.lsf").read_text(encoding="utf-8") != launcher(ranks):
        raise ValueError("SCF chain requires the exact reviewed launcher/ranks")
    if (workdir / "INCAR").read_bytes() != (workdir / "A.INCAR").read_bytes():
        raise ValueError("root INCAR must match stage A")
    with zipfile.ZipFile(workdir / "scf_chain_runtime.pyz") as archive:
        expected = runtime_contents()
        if sorted(archive.namelist()) != sorted(expected):
            raise ValueError("unexpected/duplicate portable runtime members")
        if any(archive.read(name) != data for name, data in expected.items()):
            raise ValueError("portable runtime differs from reviewed repository code")
    return {"passed": True, "manifest_sha256": sha256_file(workdir / "scf_chain.json"),
            "additional_files": list(INPUTS), "stages": manifest["stages"],
            "policy": manifest["policy"], "potcar_sha256": manifest["potcar_sha256"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build_runtime(args.output)
    print(f"runtime_sha256={sha256_file(args.output)}")


if __name__ == "__main__":
    main()
