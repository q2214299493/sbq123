"""Record exact review/repair evidence without accepting or submitting calculations."""
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.artifact_io import sha256_file, write_json
from scripts.state_manager.models import validate_event

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_five_c2_adsorption_20261006"


def main():
    now = datetime.now(timezone.utc).isoformat()
    review_path = BASE / "gpu_supplement_review_v1/review.json"
    repair_path = BASE / "supplement_repair_v1/repair_review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    repair = json.loads(repair_path.read_text(encoding="utf-8"))
    assert review["selected"] == ["01_extra1", "02_extra2", "03_extra1"]
    assert not review["submit_vasp"] and not repair["gpu_submitted"]
    assert sha256_file(ROOT / repair["structure_path"]) == repair["structure_sha256"]
    validation = BASE / "gpu_supplement_review_v1/validation_summary.json"
    if validation.exists():
        raise FileExistsError(validation)
    write_json(validation, {
        "recorded_at": now, "python_syntax": "PASS", "focused_ruff": "PASS",
        "pytest": {"passed": 12, "command": "python -m pytest tests/test_fe110_c2_supplement.py tests/test_fe110_c2_review_repair.py -q"},
        "five_return_hash_schema_exit_checkpoint_validations": "PASS",
        "chemistry": {"intact": 4, "fragmented": 1},
        "duplicate_review": {"distinct_new_candidates": 3, "live_VASP_geometry_match_standby": 1},
        "repair": "GEOMETRY_PASS_WITHOUT_WARNINGS_NOT_RELAXED",
        "figure_inspection": "PASS", "scientific_acceptance": False,
        "remaining": ["secondary off-symmetry site warnings require review", "repair ML relaxation",
                      "VASP final chemistry/sites/convergence", "compatible accepted energy registration"],
    })
    old_id = "task-fe110-five-c2-adsorption-supplement-gpu2142-submitted-20261006"
    old = json.loads((ROOT / f"modules/state_handoff/events/{old_id}.json").read_text(encoding="utf-8"))
    new_id = "task-fe110-five-c2-adsorption-gpu2142-reviewed-repair-20261007"
    references = [review_path.relative_to(ROOT).as_posix(), repair_path.relative_to(ROOT).as_posix(),
                  "docs/reviews/fe110_gpu2142_adsorption_review_20261007.md"]
    event = {
        "schema_version": 1, "event_id": new_id, "occurred_at": now, "recorded_at": now,
        "event_type": "task_updated", "entity": old["entity"],
        "summary": "GPU2142 outputs reviewed; three distinct intact predicted candidates, one possible duplicate standby, and one rebuilt CHCO initial geometry; no new jobs.",
        "evidence": [{"locator": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p),
                      "authority": a, "observed_at": now} for p, a in (
            (review_path, "module_validation"), (repair_path, "module_validation"),
            (ROOT / repair["structure_path"], "structure_output"), (validation, "module_validation"),
            (ROOT / "docs/reviews/fe110_gpu2142_adsorption_review_20261007.md", "repository_document"))],
        "review": {"required": False, "reason_codes": [], "status": "not_required"},
        "payload": {**old["payload"], "phase": "active",
            "current_evidence": [
                "All5GPU2142producer exit records report0 and returned hashes/schema/checkpoint/source identities validate; no durable Slurm terminal state claimed.",
                "All5reach MLfmax0.10eV/A, but03_extra2breaks CC1.5349->2.9355A intoCH+CO; failed input/output preserved, not accepted as targetCHCO.",
                "01_extra1,02_extra2,03_extra1 are intact and distinct from sampled previousGPU/VASP geometries; secondary CH2-C45/O47 off-symmetry site warnings retained, not final-site acceptance.",
                "02_extra1RMSD0.18567A to the sampled live02_cfg2VASP structure; hold as possible duplicate, not proven same final minimum and no source deletion.",
                "Duplicate review uses36clean-slab top-side-preserving symmetries,xyPBC,Hpermutations,actual relaxed height; never compare ML and DFT absolute energies.",
                "One new03_extra2_repair_v1 uses intact exactCARE template,centralC46shortbridge,flat chain alongFe rows,C46-Fe2.20A; canonical geometry passes without warnings,minimum seed-motifRMSD0.40653A.",
                "Repair is unrelaxed; no bonds forced, no model fine-tuning and no DFT protocol change. Original45Fe slab and fixedFe0-17 preserved.",
                "Python syntax,Ruff,12related tests and figure inspection pass; existing10VASP jobs untouched. No new GPU/VASP submission or accepted-energy registration."],
            "one_executable_step": "Review the rebuilt CHCO seed with the user and obtain separate authorization for one bounded AQCat25 pre-relaxation; retain three distinct intact GPU candidates for later VASP input review and hold02_extra1.",
            "submission_boundary": "User authorized review/deduplication and one geometry repair only. No new GPU/VASP execution, stop, resubmit, model fine-tuning or accepted-result promotion.",
            "authoritative_references": old["payload"]["authoritative_references"] + references},
        "supersedes": [old_id],
    }
    validate_event(event)
    target = ROOT / f"modules/state_handoff/events/{new_id}.json"
    if target.exists():
        raise FileExistsError(target)
    write_json(target, event)
    print(target.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
