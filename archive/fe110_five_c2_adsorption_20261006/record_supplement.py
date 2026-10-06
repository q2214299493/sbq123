"""Persist factual local construction evidence; no scientific acceptance or submission."""
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.artifact_io import sha256_file, write_json
from scripts.state_manager.models import validate_event

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_five_c2_adsorption_20261006"
DEST = BASE / "supplement_v1"


def main():
    now = datetime.now(timezone.utc).isoformat()
    validation_path = DEST / "validation_summary.json"
    if validation_path.exists():
        raise FileExistsError("Preserve recorded validation bytes")
    write_json(validation_path, {
        "python_syntax": "PASS", "focused_ruff": "PASS", "pytest": {"passed": 4},
        "five_exported_POSCAR_reparse_hash_cell_Fe_positions_flags_connectivity": "PASS",
        "five_canonical_geometry_reviews": "PASS_WITHOUT_WARNINGS",
        "symmetry_and_height_duplicate_review": "PASS_DISTINCT_STARTS_ONLY",
        "figure_inspection": "PASS", "GPU_or_VASP_execution": "NOT_RUN",
        "remaining": ["user structure review", "GPU relaxation and domain/chemistry review", "final VASP validation"],
    })
    old_id = "task-fe110-five-c2-adsorption-vasp-submitted-20261006"
    old = json.loads((ROOT / f"modules/state_handoff/events/{old_id}.json").read_text())
    new_id = "task-fe110-five-c2-adsorption-supplement-reviewed-20261006"
    event = {
        "schema_version":1, "occurred_at":now, "recorded_at":now, "event_id":new_id,
        "event_type":"task_updated", "entity":old["entity"],
        "summary":"Five additional intact local-template adsorption starting candidates constructed for user review; no new jobs.",
        "evidence":[{"locator":p.relative_to(ROOT).as_posix(), "sha256":sha256_file(p),
                     "authority":a, "observed_at":now} for p,a in (
            (Path(__file__).with_name("supplement_plan.json"), "repository_document"),
            (DEST / "candidate_review.json", "module_validation"),
            (validation_path, "module_validation"),
            (DEST / "structure_review.png", "structure_output"),
            (Path(__file__).with_name("SUPPLEMENT_REVIEW.md"), "repository_document"))],
        "review":{"required":False, "reason_codes":[], "status":"not_required"},
        "payload":{**old["payload"], "phase":"active",
            "current_evidence":old["payload"]["current_evidence"] + [
                "User requested supplementation. Five additional candidates01_extra1,02_extra1/2,03_extra1/2 built from exact local templates, not externally proven minima.",
                "All5exported initial geometries pass canonical chemistry/contacts/cell/fixed-layer review; clean-slab symmetry and H permutation checks exclude periodic/reflection/height-only duplicates.",
                "Nominal input counts would be3/3/3/3/3; the new5are not relaxed and may merge or fragment later. Existing10VASP jobs unchanged; no fresh scheduler observation in this step.",
                "Python syntax,Ruff,4bounded tests and5POSCAR reparse checks pass. NewGPU/VASP submissions remain unauthorized."],
            "one_executable_step":"Review the five supplemental structures with the user; after separate authorization prepare/run a bounded AQCat25 batch and return results for chemistry/domain/duplicate review.",
            "submission_boundary":"Existing10VASP jobs unchanged. Five new initial structures await review; no new GPU/VASP execution or automatic resubmission authorized.",
            "authoritative_references":old["payload"]["authoritative_references"] + [
                "archive/fe110_five_c2_adsorption_20261006/SUPPLEMENT_REVIEW.md",
                "calculations/fe110_five_c2_adsorption_20261006/supplement_v1/candidate_review.json",
                "calculations/fe110_five_c2_adsorption_20261006/supplement_v1/structure_review.png"]},
        "supersedes":[old_id],
    }
    target = ROOT / f"modules/state_handoff/events/{new_id}.json"
    assert not target.exists()
    validate_event(event)
    write_json(target, event)
    print(str(target))


if __name__ == "__main__":
    main()
