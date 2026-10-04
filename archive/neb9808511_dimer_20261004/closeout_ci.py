"""Preserve stopped CI evidence and register only its observed SCF failure."""
import io
import argparse
import shutil
import subprocess
import tarfile

import numpy as np
from ase.geometry import find_mic
from scripts.artifact_io import write_json, sha256_file, load_json_object
from scripts.neb_agent.analyze_neb_outputs import analyze
from scripts.neb_agent.diagnose_path_geometry import diagnose
from scripts.neb_agent.utils_structure import read_poscar, copy_with_frac, write_poscar
from scripts.ts_strategy_engine.strategy_learning import import_failure, retry_assessment
from scripts.ts_strategy_engine.learning_evidence import bind_files, attempt_input_hashes
from archive.neb9808511_dimer_20261004.prepare_dimer import ROOT, RECORD, PARENT


def main():
    raw = PARENT / "stopped_review_20261004"
    if raw.exists():
        raise FileExistsError("Closeout exists; reconcile before retrying")
    remote = "~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/" + PARENT.name
    names = ["INCAR", "KPOINTS", "00/POSCAR", "10/POSCAR"]
    names += [f"{i:02d}/{name}" for i in range(1, 10) for name in ("POSCAR", "CONTCAR", "OUTCAR", "OSZICAR")]
    command = f"cd {remote} && tar czf - " + " ".join(names)
    result = subprocess.run(["ssh", "sunboquan-codex", command], capture_output=True, timeout=60, check=True)
    if len(result.stdout) > 128 * 1024 * 1024:
        raise ValueError("Unexpected evidence size")
    raw.mkdir()
    with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:gz") as archive:
        for member in archive.getmembers():
            target = raw / member.name
            if not member.isfile() or member.name not in names or not target.resolve().is_relative_to(raw.resolve()):
                raise ValueError("Unexpected tar member")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.extractfile(member).read())
    movie = subprocess.run(["ssh", "sunboquan-codex", f'cd {remote} && perl "$HOME/soft/qvasp-v2.2/exefile/Tools/USERTooLs/vtstscripts/nebmovie.pl" 1 && test -s movie'],
                           capture_output=True, timeout=45, check=True)
    write_json(raw / "nebmovie1_receipt.json", {"returncode": movie.returncode, "stdout": movie.stdout.decode(errors="replace"),
                                                "stderr": movie.stderr.decode(errors="replace"), "remote_dir": remote})
    threshold = ROOT / "configs/neb_agent/default_thresholds.yaml"
    analysis = analyze(raw, threshold, [49])
    normalized = raw / "normalized_geometry"
    last = None
    translations = []
    for i in range(11):
        source = raw / f"{i:02d}" / ("POSCAR" if i in (0, 10) else "CONTCAR")
        s = read_poscar(source)
        shift = np.zeros_like(s.frac)
        if last is not None:
            delta, _ = find_mic((s.frac - last.frac) @ s.cell, s.cell, pbc=True)
            target = last.frac + delta @ np.linalg.inv(s.cell)
            shift = np.rint(target - s.frac)
            if np.any(shift[:18]) or np.abs(target - s.frac - shift).max() > 1e-8:
                raise ValueError("Non-integer or fixed-atom shift")
        last = copy_with_frac(s, s.frac + shift, s.comment)
        write_poscar(normalized / f"{i:02d}/POSCAR", last)
        translations.append({"image": f"{i:02d}", "source_sha256": sha256_file(source), "integer_shifts": shift.tolist()})
    shutil.copyfile(raw / "INCAR", normalized / "INCAR")
    geometry = diagnose(normalized, ["49"], [str(i) for i in range(18)], threshold, expected_interior=9)
    write_json(normalized / "normalization_receipt.json", {"scope": "Integer translations only, no geometry repair", "rows": translations})
    register(raw, analysis, geometry)


def register(raw, analysis, geometry):
    if (RECORD / "ci_failure_registration.json").exists():
        raise FileExistsError("Failure already recorded; inspect receipt")
    inputs = {name: str(PARENT / name) for name in ("INCAR", "KPOINTS", "POTCAR.spec", "script.lsf")}
    inputs.update({f"{i:02d}/POSCAR": str(PARENT / f"{i:02d}/POSCAR") for i in range(11)})
    observations = [{"path": str(raw / "neb_analysis.json"), "sha256": sha256_file(raw / "neb_analysis.json"),
                     "pointer": "/scf_exhausted_images", "value": analysis["scf_exhausted_images"]},
                    {"path": str(RECORD / "scheduler_after.json"), "sha256": sha256_file(RECORD / "scheduler_after.json"),
                     "pointer": "/status", "value": "EXIT"}]
    row = next(row for row in analysis["images"] if row["image"] == "06")
    if analysis["scf_exhausted_images"] != ["06"] or row["scf_iterations_last10"].count(200) < 5:
        raise ValueError("Review required; repeated completed SCF exhaustion not verified")
    spec = {"attempt_id": "ci9826728_scf_failure_20261004", "task_id": "fe110_c2ho_h_migration_ISA9725473_to_INT06_9748648",
            "kind": "ci_neb", "inputs": inputs, "outcome": {"status": "failure", "failure_class": "scf",
            "root_cause_status": "confirmed", "deterministic": True,
            "reviewer": "Codex: repeated observed NELM exhaustion in image06; exact-input retry blocked. Physical cause remains unproven; no model-error claim.",
            "observations": observations, "costs": {}, "ts_template_id": None}}
    write_json(RECORD / "ci_failure_import_request.json", spec)
    attempt = import_failure(ROOT / "data/project_registry.sqlite3", spec)
    retry = retry_assessment(ROOT / "data/project_registry.sqlite3", "ci_neb", attempt_input_hashes("ci_neb", bind_files(inputs)))
    write_json(RECORD / "ci_failure_registration.json", {"attempt_id": attempt, "geometry_status": geometry["status"],
                                                         "scf_exhausted_images": analysis["scf_exhausted_images"],
                                                         "canonical_scf_failure_flag": analysis["scf_failure"],
                                                         "retry_assessment": retry, "training_authorized": False})
    print("Failure recorded", attempt, "geometry", geometry["status"], "retry", retry["status"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--register-existing", action="store_true")
    args = parser.parse_args()
    if args.register_existing:
        raw = PARENT / "stopped_review_20261004"
        register(raw, load_json_object(raw / "neb_analysis.json"),
                 load_json_object(raw / "normalized_geometry/path_geometry_diagnosis.json"))
    else:
        main()
