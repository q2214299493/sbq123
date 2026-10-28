"""Independent prepared-input replay;no VASP or GPU execution."""
from pathlib import Path

from pymatgen.io.vasp.inputs import Incar

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid, write_json_exclusive
from .prepare_c2_dft import ARMS, CUSTODIAN, DEST, OUTPUT, PACKAGE, PROFILE, ROOT, check_three_arms


def verify():
    plan_path = DEST / "plan.json"
    plan = load_json_object(plan_path)
    if not source_file_manifest_valid(plan):
        raise ValueError("prepared input/source bytes changed")
    if (plan["job_count"] != 3 or [row["arm"] for row in plan["jobs"]] != list(ARMS)
            or plan["VASP_execution_authorized"] is not False or plan["ALLOWED_ACTIONS"]
            or plan["uploaded"] is not False or plan["submitted"] is not False):
        raise ValueError("three-arm/no-submission scope changed")
    request = load_json_object(PACKAGE / "request.json")
    origin = next(row for row in request["scope"]["cases"] if row["name"] == "10_A")
    rows = []
    for job in plan["jobs"]:
        folder = ROOT / job["path"]
        for name, digest in job["files"].items():
            if sha256_file(folder / name) != digest:
                raise ValueError("prepared core input hash changed")
        metadata = load_json_object(folder / "candidate_manifest.json")
        if metadata["common_original_seed_sha256"] != origin["seed_sha256"]:
            raise ValueError("original baseline changed")
        if sha256_file(folder / "POSCAR") != metadata["source_POSCAR_sha256"]:
            raise ValueError("source coordinates were edited during preparation")
        model = None if job["arm"] == "direct_dft" else job["arm"].removesuffix("_then_dft")
        if (metadata["ML_performed"] is not (model is not None)
                or metadata["model_checkpoint_sha256"] != (request["scope"]["models"][model]["sha256"] if model else None)):
            raise ValueError("direct/ML provenance mislabeled")
        if model is None and (metadata["source_POSCAR_sha256"] != origin["seed_sha256"] or metadata["ML_optimizer_steps"] is not None):
            raise ValueError("pure DFT control is not the unmodified original")
        incar = Incar.from_file(folder / "INCAR")
        moments = incar["MAGMOM"]
        if (float(incar["EDIFFG"]) != -.02 or int(incar["NSW"]) != 300 or int(incar["LORBIT"]) != 11
                or len(moments) != 50 or any(abs(float(v)-2.2)>1e-12 for v in moments[:45])
                or any(float(v)!=0 for v in moments[45:])):
            raise ValueError("force/step/local-moment/spin initialization differs")
        custodian = load_json_object(folder / "custodian.stdout")
        report = load_json_object(folder / "submission_preflight.json")
        if (custodian["status"] != "VALIDATION_ONLY" or custodian["blockers"] or not report["passed"]
                or report["bundle_sha256"] != job["bundle_sha256"] or report["files"] != job["files"]):
            raise ValueError("preflight/source report differs")
        rows.append({"arm": job["arm"], "POSCAR_sha256": metadata["source_POSCAR_sha256"], "ML_performed": metadata["ML_performed"],
            "bundle_sha256": job["bundle_sha256"], "C_C_A": job["geometry"]["C_C_distance_A"], "passed": True})
    result = {"status": "PASS_C2_THREE_ARM_INPUT_SOURCE_METHOD_AND_MAGMOM_REPLAY", "jobs": rows,
        "core_inputs_hash_verified": sum(len(row["files"]) for row in plan["jobs"]), "same_method_resource_checks": check_three_arms(DEST),
        "direct_arm_original_bytes_and_no_ML_verified": True, "same_DFT_minimum_assumed": False,
        "POTCAR_actual_remote_hash_verified_this_step": False, "DFT_executed": False,
        "source_files": source_file_manifest([Path(__file__), plan_path, PROFILE, CUSTODIAN, OUTPUT / "ML_results_review.json", PACKAGE / "request.json"])}
    write_json_exclusive(DEST / "input_verification.json", result)
    print({k: result[k] for k in ["status", "core_inputs_hash_verified", "direct_arm_original_bytes_and_no_ML_verified", "jobs"]}, flush=True)


if __name__ == "__main__":
    verify()
