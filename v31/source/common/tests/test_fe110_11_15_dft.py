"""Local geometry/budget guard and duplicate-submission refusal, without execution."""
import shutil

import pytest

from archive.fe110_11_15_gpu_20261029 import dft
from archive.fe110_11_15_gpu_20261029 import complete_dft
from scripts.artifact_io import sha256_file
from scripts.registry_schema import migrate_registry
from scripts.vasp_inputs import build_fe110_adsorption_relaxation


@pytest.mark.parametrize("mutation", [None, "step_budget", "fixed_mask"])
def test_independent_readback_checks_geometry_and_budget(tmp_path, monkeypatch, mutation):
    database = tmp_path / "learning.sqlite3"
    migrate_registry(database)
    real_preflight = dft.preflight
    monkeypatch.setattr(dft, "preflight", lambda folder, kind, **kwargs:
        real_preflight(folder, kind, learning_database=database, **kwargs))
    source = dft.BASE / "candidates_v5/11_A/POSCAR"
    shutil.copyfile(source, tmp_path / "POSCAR")
    build_fe110_adsorption_relaxation(tmp_path, screening=True, write_local_moments=True)
    (tmp_path / "candidate_manifest.json").write_text('{"relaxation_stage":"screening","write_local_moments":true}', encoding="ascii")
    if mutation == "step_budget":
        path = tmp_path / "INCAR"
        path.write_text(path.read_text().replace("NSW = 80", "NSW = 81"), encoding="ascii")
    elif mutation == "fixed_mask":
        path = tmp_path / "POSCAR"
        path.write_text(path.read_text().replace("F F F", "T T T", 1), encoding="ascii")
    if mutation:
        with pytest.raises(ValueError):
            dft.validate_input(tmp_path, source, source)
    else:
        assert dft.validate_input(tmp_path, source, source)["readback"] == "PASS"


@pytest.mark.parametrize("mutation", [None, "hash", "eligibility", "missing_case"])
def test_review_binding_cannot_silently_expand_scope(tmp_path, monkeypatch, mutation):
    pose = tmp_path / "POSCAR"
    pose.write_bytes(b"hash guard fixture, not a submitted structure")
    rows = [{"name": n, "selected_for_DFT": str(pose), "selected_POSCAR_sha256": sha256_file(pose), "ML_endpoint_eligible": True} for n in dft.NAMES]
    review = {"cases": rows, "DFT_representatives": rows.copy(), "duplicates": []}
    if mutation == "hash":
        rows[0]["selected_POSCAR_sha256"] = "a" * 64
    elif mutation == "eligibility":
        rows[0]["ML_endpoint_eligible"] = False
    elif mutation == "missing_case":
        rows.pop()
    monkeypatch.setattr(dft, "load_json_object", lambda _: review)
    monkeypatch.setattr(dft, "source_file_manifest_valid", lambda _: True)
    if mutation:
        with pytest.raises(ValueError):
            dft.reviewed_cases()
    else:
        assert len(dft.reviewed_cases()) == 15


def test_existing_reservation_never_resubmitted(tmp_path, monkeypatch):
    monkeypatch.setattr(dft, "load_json_object", lambda _: {"jobs": [{"directory": str(tmp_path)}]})
    monkeypatch.setattr(dft, "source_file_manifest_valid", lambda _: True)
    monkeypatch.setattr(dft, "submission_status", lambda _: {"status": "SUBMITTED"})
    def forbidden(*args, **kwargs):
        pytest.fail("reserved job must not reach an executor")
    monkeypatch.setattr(dft, "submit", forbidden)
    with pytest.raises(ValueError, match="prior or ambiguous"):
        dft.execute()


@pytest.mark.parametrize("ambiguous", [False, True])
def test_partial_completion_requires_six_receipts_and_nine_unreserved(tmp_path, monkeypatch, ambiguous):
    ready = {"jobs": [{"name": n, "directory": str(tmp_path / n)} for n in dft.NAMES]}
    monkeypatch.setattr(complete_dft, "load_json_object", lambda _: ready)
    monkeypatch.setattr(complete_dft, "source_file_manifest_valid", lambda _: True)
    def state(folder):
        if ambiguous and folder.name == "13_A":
            return {"status": "UNKNOWN"}
        return {"status": "NOT_RESERVED" if folder.name in complete_dft.NINE else "SUBMITTED"}
    monkeypatch.setattr(complete_dft, "submission_status", state)
    if ambiguous:
        with pytest.raises(ValueError, match="prior state changed"):
            complete_dft.prior_state()
    else:
        assert len(complete_dft.prior_state()["jobs"]) == 15
