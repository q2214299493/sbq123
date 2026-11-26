"""Read-only replay of the first oxide initialization attempt, including its native fatal error."""
import json
from pathlib import Path
from zipfile import ZipFile

from scripts.artifact_io import sha256_bytes, sha256_file

STAGE = Path(__file__).resolve().parents[1] / "reports/multiphase/stage_b2_3_2_4"
EVIDENCE = STAGE / "native_acceptance"


def read(name):
    return json.loads((EVIDENCE / name).read_bytes())


def test_consumed_single_launch_links_to_exact_authorized_bytes():
    receipt = read("execution_receipt.json")
    approval = read("execution_approval.json")
    claim = read("consumed.json")
    request = json.loads((STAGE / "approval_request.json").read_bytes())
    assert receipt["plan_sha256"] == claim["state_sha256"] == approval["state_sha256"] == sha256_file(STAGE / "execution_plan.json")
    assert receipt["approval_sha256"] == claim["approval_sha256"] == sha256_file(EVIDENCE / "execution_approval.json")
    assert receipt["approval_source_sha256"] == approval["source_sha256"] == sha256_file(EVIDENCE / approval["source_file"])
    assert receipt["consumed_claim_sha256"] == sha256_file(EVIDENCE / "consumed.json")
    assert receipt["gate_accepted"] and receipt["output_directory_new_and_empty_before_staging"]
    assert approval["ALLOWED_ACTIONS"] == [receipt["gate_action"]] == [request["requested_action"]]
    assert not receipt["already_consumed_before_claim"] and receipt["input_files_intact_after_exit"]
    assert receipt["launch_count"] == approval["maximum_launches"] == claim["launch_limit"] == 1
    assert receipt["retry_count"] == claim["retries"] == 0 and not receipt["timed_out"]
    assert receipt["bound_limits"] == request["limits"]
    assert receipt["command"][1:] == ["--max_steps=0", "--wall_time=15"]
    assert receipt["environment_overrides"] == {"OMP_NUM_THREADS": "1"}


def test_full_byte_archive_matches_published_inputs_and_capture_receipt():
    manifest = read("io_manifest.json")
    receipt = read("execution_receipt.json")
    assert manifest["raw_archive_sha256"] == sha256_file(EVIDENCE / "raw_native.zip")
    assert manifest["approved_input_manifest_sha256"] == sha256_file(STAGE / "native/input_manifest.json")
    original = json.loads((STAGE / "native/input_manifest.json").read_bytes())["files_sha256"]
    assert receipt["staged_input_sha256"] == original
    with ZipFile(EVIDENCE / "raw_native.zip") as archive:
        assert archive.testzip() is None
        assert sorted(row["member"] for row in manifest["members"]) == sorted(archive.namelist())
        inputs = {}
        for row in manifest["members"]:
            name = Path(row["member"]).name
            raw = archive.read(row["member"])
            assert len(raw) == row["size_bytes"] and sha256_bytes(raw) == row["sha256"]
            if row["role"] == "staged_input":
                assert raw == (STAGE / "native" / name).read_bytes()
                inputs[name] = row["sha256"]
            else:
                group = "console_files" if row["role"] == "capture" else "output_files"
                assert row["sha256"] == receipt[group][name]["sha256"]
        assert inputs == original


def test_fatal_native_output_overrides_zero_exit_status():
    verdict = read("validation.json")
    with ZipFile(EVIDENCE / "raw_native.zip") as archive:
        general = archive.read("native_run/general_output.txt").decode()
        assert "ZACROS 4.0" in general and "Serial run (no parallelism)." in general
        assert "ABNORMAL TERMINATION DUE TO FATAL ERROR" in general and "> Normal termination <" not in general
        assert "Error code 1002 from simulation_parser_module" in general
        assert 'Invalid expression "temperature 400" in line 2.' in general
        assert "Finished reading" not in general and "Events occurred:" not in general
        assert archive.read("native_run/simulation_input.dat").splitlines()[1] == b"temperature 400"
        assert b"Maximum number of steps: 0" in archive.read("stdout.log")
        assert b"Stopping due to error" in archive.read("stderr.log")
    assert read("execution_receipt.json")["exit_code"] == 0
    assert verdict["native_initialization"] == "failed" and verdict["fatal"]["code"] == 1002
    assert [r["status"] for r in verdict["reader_acceptance"]] == ["rejected"] + ["not_reached"] * 4
    assert verdict["propagation"]["event_loop_reached"] is False
    assert verdict["propagation"]["observed_final_event_count"] is None


def test_missing_native_state_cannot_certify_structural_or_numerical_agreement():
    v = read("validation.json")
    with ZipFile(EVIDENCE / "raw_native.zip") as z:
        assert all("native_run/" + name not in z.namelist() for name in ("process_debug.txt", "restart.inf", "lattice_output.txt"))
    assert len(v["restart"]["bindings_by_site"]) == 7 and not v["restart"]["produced"]
    assert all(row["native_entity_id"] is row["native_species_id"] is row["native_leg_id"] is None
               for row in v["restart"]["bindings_by_site"])
    assert v["initial_catalogue"]["observed_adsorption"] is v["initial_catalogue"]["observed_desorption"] is None
    assert v["initial_catalogue"]["forbidden_match_absence_verified"] is None
    assert v["initial_molecular_entities"]["observed"] is v["site_inventories"]["observed"] is None
    ref = json.loads((STAGE / "numerical_reference.json").read_bytes())
    for name, row in v["numerical_agreement"]["directions"].items():
        assert row["expected_propensity_per_match_s_inv"] == ref["directions"][name]["propensity_per_match_s_inv"]
        assert row["native_propensity_per_match_s_inv"] is row["relative_error"] is None
    assert v["numerical_agreement"]["status"] == "not_evaluable"
    assert v["next_execution_authorized"] is False
