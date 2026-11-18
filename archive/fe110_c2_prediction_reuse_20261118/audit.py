"""Locate existing frozen536 predictions for two reviewed C2 coordinates."""
from pathlib import Path
import subprocess

import numpy as np
from ase.geometry import find_mic
from ase.io import read

from archive.fe110_grouped_qc_20261026.review import raw_frames
from archive.fe110_10b_lowforce_20261023.legacy_helpers import verify_frame
from archive.fe110_joint_priority_20261117.analyze import BASE, MODEL, MODEL_SHA, ROOT, guard_hashes, load, save, sha, table

RUN = BASE / "c2_prediction_reuse_20261118_v1"
PRIOR = BASE / "c2_path_reuse_20261118_v1/reviewed_v2/audit_reviewed.json"
GPU = BASE / "force_diagnosis536_gpu_20261117_v4"
PAPER = ROOT / "calculations/fe110_ch_co_to_chco_ts_20261109/paper_aqcat25_ft512_20261112_v1"


def same_coordinates(first, second):
    """Exact atom mapping and cell; periodic XY wrapping is allowed, no fitting."""
    if first.get_chemical_symbols() != second.get_chemical_symbols() or not np.allclose(first.cell, second.cell, rtol=0, atol=1e-10):
        return False
    def fixed(atoms):
        return sorted(int(i) for c in atoms.constraints for i in c.get_indices())
    if fixed(first) != fixed(second):
        return False
    _, distance = find_mic(first.positions - second.positions, first.cell, pbc=[True, True, False])
    return bool(np.max(distance) <= 1e-10)


def eligible(model_sha, reference, candidate):
    return model_sha == MODEL_SHA and same_coordinates(reference, candidate)


def metadata_search():
    query = ["rg", "-l", "-F", MODEL_SHA, "calculations", "docs/reviews", "-g", "*.json", "-g", "*.md", "-g", "*.yaml"]
    result = subprocess.run(query, cwd=ROOT, capture_output=True, text=True, encoding="utf8", check=False)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr)
    paths = sorted(ROOT / p for p in result.stdout.splitlines() if not (ROOT / p).is_relative_to(RUN))
    return {"argv": query, "exit_code": result.returncode, "files": [{"path": str(p), "size": p.stat().st_size, "sha256": sha(p)} for p in paths],
            "limitation": "registered local JSON/YAML/Markdown only;unregistered remote or binary-only caches not exhaustively searched"}


def run():
    before = guard_hashes()
    if sha(MODEL) != MODEL_SHA:
        raise ValueError("frozen model identity changed")
    prior = load(PRIOR)
    targets = [row for row in prior["records"] if row["id"] in ("paper_round000", "paper_round001")]
    if len(targets) != 2:
        raise ValueError("two source representatives required")
    prediction_path, request_path = GPU / "returned/predictions614.json", GPU / "packet/request.json"
    predictions, request = load(prediction_path), load(request_path)
    if predictions["checkpoint_sha256"] != MODEL_SHA or request["model"]["sha256"] != MODEL_SHA or predictions["request_sha256"] != sha(request_path):
        raise ValueError("614 prediction model/request binding failed")
    pred = {r["sample_id"]: r for r in predictions["samples"]}
    if len(pred) != 614 or len(request["samples"]) != 614 or set(pred) != {r["sample_id"] for r in request["samples"]}:
        raise ValueError("614 sample correspondence failed")
    bound = {PRIOR, MODEL, prediction_path, request_path, Path(__file__)}
    frames = []
    for sample in request["samples"]:
        path = GPU / "packet" / sample["structure_path"]
        if sha(path) != sample["structure_sha256"] or pred[sample["sample_id"]]["structure_sha256"] != sample["structure_sha256"]:
            raise ValueError("614 coordinate binding changed")
        bound.add(path)
        frames.append((sample, read(path, format="vasp")))
    scan = metadata_search()
    old_requests = [PAPER / "continuation_r001/original_request.json", PAPER / "continuation_r001/request.json"]
    old_returns = [PAPER / "return_13883/output", PAPER / "return_14304/output"]
    rows = []
    for index, target in enumerate(targets):
        path, outcar = Path(target["structure_path"]), Path(target["OUTCAR_path"])
        if sha(path) != target["structure_sha256"] or sha(outcar) != target["OUTCAR_sha256"]:
            raise ValueError("reviewed DFT source changed")
        atoms = read(path, format="vasp")
        frame = raw_frames(outcar, len(atoms))[0]
        force = verify_frame(atoms, frame)
        if not frame["EDIFF_marker_before_force"] or frame["ionic_step"] != target["ionic_step"]:
            raise ValueError("DFT electronic/ionic binding changed")
        matched = [s["sample_id"] for s, other in frames if eligible(predictions["checkpoint_sha256"], atoms, other)]
        old_req = load(old_requests[index])
        old_dir = old_returns[index]
        old_report = load(old_dir / "candidate_report.json")
        old_atoms = read(old_dir / "predicted_candidate.vasp", format="vasp")
        if old_report["request_sha256"] != sha(old_requests[index]) or not same_coordinates(atoms, old_atoms):
            raise ValueError("historical candidate request/coordinate binding failed")
        old_sha = old_req["checkpoint"]["sha256"]
        row = {"id": target["id"], "structure_path": str(path), "structure_sha256": target["structure_sha256"],
               "composition": "C2HO", "atom_count": len(atoms), "symbols": atoms.get_chemical_symbols(),
               "fixed_atom_indices_0based": list(range(18)), "roles_0based": {"C": [45, 46], "O": [47], "H": [48], "movable_Fe": list(range(18, 45))},
               "model_path": str(MODEL), "model_sha256": MODEL_SHA, "DFT_OUTCAR_path": str(outcar),
               "DFT_OUTCAR_sha256": target["OUTCAR_sha256"], "DFT_physical_key": target["physical_key"],
               "DFT_force_table_byte_range": target["force_table_byte_range"], "DFT_movable_fmax_eV_A": float(np.linalg.norm(force[18:], axis=1).max()),
               "matched_frozen536_prediction_samples": matched, "matching_method": "same symbols/order,fixed mask,cell,XY_MIC max displacement<=1e-10A;no fit or near-duplicate substitution",
               "historical_same_coordinate_prediction": {"report_path": str(old_dir / "candidate_report.json"), "request_path": str(old_requests[index]),
                                                          "checkpoint_sha256": old_sha, "ML_fmax_eV_A": old_report["predicted_movable_fmax_eV_per_A"],
                                                          "same_coordinates_verified": True, "reuse_as_frozen536": eligible(old_sha, atoms, old_atoms),
                                                          "rejection_reason": "CHECKPOINT_SHA256_MISMATCH" if old_sha != MODEL_SHA else None},
               "status": "PENDING_INFERENCE_NO_MATCH_IN_AUDITED_RECORDS" if not matched else "EXISTING_FROZEN536_PREDICTION_FOUND",
               "frozen536_ML_fmax_eV_A": None, "frozen536_DFT_vector_RMSE_eV_A": None,
               "force_unit": "eV/Angstrom", "execution_authorized": False, "new_DFT_needed_for_reference": False,
               "scope": "existing_training_family_diagnostic;not independent heldout;no partition admission"}
        if matched:
            raise ValueError("matching predictions found:perform owning force comparison before finalizing")
        bound.update([path, outcar, old_requests[index], old_dir / "candidate_report.json", old_dir / "predicted_candidate.vasp"])
        rows.append(row)
    if guard_hashes() != before:
        raise ValueError("frozen guards changed")
    output = RUN / "results_v2"
    output.mkdir(parents=True, exist_ok=False)
    save(output / "audit.json", {"records": rows, "metadata_search": scan, "verified_614_geometries": len(frames),
                             "source_hashes": {str(p): sha(p) for p in sorted(bound)}, "frozen_before": before, "frozen_after": guard_hashes(),
                             "inference_performed": False, "training_performed": False, "DFT_submitted": False})
    save(output / "pending_inference_list.json", {"document_kind": "read_only_pending_inference_inventory_not_execution_request",
         "model": {"path": str(MODEL), "sha256": MODEL_SHA}, "samples": rows, "execution_authorized": False,
         "proposed_inference_contract": "same frozen536 native ASE FP32,eval,tags0,raw forces apply_constraint=False;all49 atoms saved,fixed18 excluded from metrics",
         "host_selected": None, "GPU_job_submitted": False, "DFT_budget_for_these_existing_labels": 0})
    table(output / "两个代表预测核查及待推理清单.csv", rows, [("id", "代表ID"), ("structure_path", "原始坐标"),
          ("structure_sha256", "坐标SHA256"), ("model_sha256", "目标模型SHA256"), ("DFT_movable_fmax_eV_A", "DFT最大可动力_eV_A"),
          ("matched_frozen536_prediction_samples", "已匹配冻结536预测"), ("historical_same_coordinate_prediction", "历史同坐标预测排除依据"),
          ("status", "状态"), ("frozen536_DFT_vector_RMSE_eV_A", "冻结536与DFT力误差_未知"), ("execution_authorized", "执行授权")])
    print({"verified_frames": len(frames), "metadata_matches": len(scan["files"]), "eligible_predictions": sum(len(r["matched_frozen536_prediction_samples"]) for r in rows),
           "pending": len(rows), "rows": [(r["id"], r["DFT_movable_fmax_eV_A"], r["historical_same_coordinate_prediction"]["checkpoint_sha256"]) for r in rows]})


if __name__ == "__main__":
    run()
