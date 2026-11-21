"""Offline native-rate adapters against separate MAT runs and all archived KMC windows."""
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from scripts.artifact_io import sha256_bytes, sha256_file
from scripts.baseline_mkm import rate_adapter as cat
from scripts.kinetic_data.stoichiometric_sources import generate_source_terms
from scripts.rate_output_v2 import validate_rate_output_v2
from scripts.surface_kmc import rate_adapter as kmc
from scripts.surface_kmc.trajectory_statistics import process_samples

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "reports/multiphase"
CYCLE = BASE / "phase2_5_2"
POINT = BASE / "phase3_0"
KMC = BASE / "phase2_5_1"
OUT = BASE / "stage_b1_4"
MATRIX = KMC / "zacros_validation.json"
NETWORK = ROOT / "tests/fixtures/multiphase/kinetic_interface_network.json"


def cat_inputs(phase):
    original = phase == "phase2_5_2"
    return (CYCLE / "catkinas_closed_cycle_validation.json" if original else POINT / "benchmark_manifest.json",
            dict(network_path=POINT / "closed_cycle_network.json", dataset_path=CYCLE / "cycle_dataset.json",
                 config_path=CYCLE / "cycle_configuration.json" if original else POINT / "workflow_configuration.json",
                 input_path=CYCLE / "catkinas_closed_cycle_input.m", normalization_path=BASE / "phase3_1/benchmark_normalization.json",
                 root=ROOT))


def kmc_network(case):
    return OUT / "networks" / f"{case}.json" if case in {"dent", "attractive"} else NETWORK


def check_snapshot(payload, q, engine, name):
    def encoded(x):
        return (json.dumps(x, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode()
    assert (OUT / "replay" / f"{engine}-{name}.json").read_bytes() == encoded(payload)
    qualifications = json.loads((OUT / f"{engine}_qualification.json").read_bytes())
    assert q == qualifications[name]
    assert payload["source_terms"] == generate_source_terms(payload["reaction_rates"])
    assert payload["validation"] == {"status": "unreviewed", "review": None}


@pytest.mark.parametrize("phase", ["phase2_5_2", "phase3_0"])
def test_catkinas_archived_native_replay(phase):
    receipt, options = cat_inputs(phase)
    payload, q = cat.adapt(receipt, **options)
    assert (payload, q) == cat.adapt(receipt, **options)
    check_snapshot(payload, q, "catkinas", phase)
    validate_rate_output_v2(payload, network=json.loads(options["network_path"].read_bytes()))
    assert payload["engine"] == {"name": "CATKINAS", "version": "20230524"}
    assert q["distribution_label"] == "20261106"
    assert payload["provenance"]["native_output"]["sha256"] == sha256_file(receipt.parent / "data1.mat")
    assert q["sites_per_reference"] == {"top-Ni": 1, "bridge-Cu": 1}
    assert payload["conditions"]["pressure_Pa"] == 160000
    assert payload["native_normalization"]["basis_kind"] == "reference_site_pair"
    assert q["overall_turnover_per_pair_s"] == 81.5127701616477
    assert q["mean_turnover_per_individual_site_s"] == 40.75638508082385
    gas = {r["species_id"]: r["net_production_rate"] for r in payload["source_terms"]["species"]}
    assert gas["HNO-g"] == q["native_gas_rates"]["HNO"] == 163.0255403232954
    assert {r["site_id"]: r["net_vacancy_rate"] for r in payload["source_terms"]["site_inventories"]} == {"top-Ni": 0, "bridge-Cu": 0}
    pair = next(r for r in payload["rate_coefficients"] if r["reaction_id"] == "ads")
    assert (pair["forward"]["value"], pair["forward"]["unit"]) == (1062.5334512545078, "bar^-1 s^-1")
    assert pair["reverse"]["value"] == 58.39820737222975
    assert q["native_convergence"] == "converged" and q["statistical_uncertainty"] is None
    assert "10^-1001" in q["native_residue_text"][0]
    for r in payload["reaction_rates"]:
        assert r["forward"] - r["reverse"] == pytest.approx(r["net"], rel=1e-12)


@pytest.mark.parametrize("key,wrong", [("input_path", "catkinas_standalone_step_assessment.md"), ("config_path", "cycle_dataset.json")])
def test_catkinas_rejects_wrong_bound_artifact(key, wrong):
    receipt, options = cat_inputs("phase3_0")
    options[key] = CYCLE / wrong
    with pytest.raises(ValueError, match="SHA-256"):
        cat.adapt(receipt, **options)


def test_distinct_mat_and_run_identity():
    points = []
    for phase in ("phase2_5_2", "phase3_0"):
        receipt, options = cat_inputs(phase)
        points.append(cat.adapt(receipt, **options)[0])
    a, b = points
    assert a["reaction_rates"] == b["reaction_rates"] and a["dataset_version"] == b["dataset_version"]
    assert a["output_binding"]["dataset_id"] != b["output_binding"]["dataset_id"]
    assert a["output_binding"]["run_id"] != b["output_binding"]["run_id"]
    assert a["provenance"]["native_output"]["sha256"] != b["provenance"]["native_output"]["sha256"]


CASES = {"mono": (0, 19, 13, 6), "dent": (0, 19, 13, 6), "full": (0, 19, 8, 11), "interacting": (0, 19, 8, 11),
         "attractive": (0, 8, 8, None), "continuous": (0, 19, 13, 6), "split": (0, 7, 6, 1), "resume": (8, 19, 6, 5)}


@pytest.mark.parametrize("case", CASES)
def test_zacros_window_and_qualification(case):
    network = kmc_network(case)
    payload, q = kmc.adapt(MATRIX, case, network, root=ROOT)
    assert (payload, q) == kmc.adapt(MATRIX, case, network, root=ROOT)
    check_snapshot(payload, q, "zacros", case)
    validate_rate_output_v2(payload, network=json.loads(network.read_bytes()))
    first, last, fwd, rev = CASES[case]
    window = q["process_window"]
    assert (window["first_event"], window["last_event"]) == (first, last)
    assert q["event_counts"]["r1_forward"] == fwd
    assert q["seed"] == 13201 and q["lattice_site_count"] == 18
    assert payload["native_normalization"]["basis_kind"] == "simulation_cell"
    assert q["steady_state"] is q["statistical_uncertainty"] is None
    observed = payload["reaction_rates"][0]
    duration = window["end_s"] - window["start_s"]
    assert observed["forward"] == fwd / duration
    if rev is None:
        assert observed["reverse"] == "not_applicable" and q["terminal_physical_time_s"] is None
        assert q["absorbing_clock_sentinel"] and q["terminal_event_counter"] == 9
    else:
        assert q["event_counts"]["r2_reverse"] == rev and observed["reverse"] == rev / duration
    assert observed["net"] == (fwd - (rev or 0)) / duration
    assert q["first_sample_counts"]["H2-g"] + q["net_species_changes"]["H2-g"] == q["last_sample_counts"]["H2-g"]
    for row in payload["source_terms"]["species"]:
        assert row["net_production_rate"] == pytest.approx(q["net_species_changes"][row["species_id"]] / duration)
    for row in payload["source_terms"]["site_inventories"]:
        assert row["net_vacancy_rate"] == -observed["net"]
    if case == "resume":
        assert q["checkpoint"]["writer_case"] == "split" and q["terminal_event_counter"] == 20


def test_zacros_rejects_a_different_network_and_an_archive_substitution(tmp_path):
    with pytest.raises(ValueError, match="network binding"):
        kmc.adapt(MATRIX, "dent", NETWORK, root=ROOT)
    receipt = json.loads(MATRIX.read_bytes())
    receipt["cases"]["mono"]["archive"] = "other.zip"
    (tmp_path / "other.zip").write_bytes((KMC / "benchmarks/full.zip").read_bytes())
    local = tmp_path / "receipt.json"
    local.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="SHA-256"):
        kmc.adapt(local, "mono", NETWORK, root=tmp_path)


@pytest.mark.parametrize("which", ["undeclared", "declared_but_missing", "wrong_member_hash", "zero_duration"])
def test_missing_process_evidence_and_corruption(tmp_path, which):
    receipt = json.loads(MATRIX.read_bytes())
    record = receipt["cases"]["mono"]
    dst = tmp_path / "sample.zip"
    name = "procstat_output.txt"
    with ZipFile(KMC / record["archive"]) as source, ZipFile(dst, "w", ZIP_DEFLATED) as target:
        for member in source.namelist():
            if member != name:
                target.writestr(member, source.read(member))
            elif which == "zero_duration":
                raw = b"\n".join(source.read(member).splitlines()[:4]) + b"\n"
                record["outputs_sha256"][name] = sha256_bytes(raw)
                target.writestr(member, raw)
            elif which == "wrong_member_hash":
                target.writestr(member, source.read(member) + b" ")
    if which == "undeclared":
        del record["outputs_sha256"][name]
    record.update(archive=dst.name, archive_sha256=sha256_file(dst))
    local = tmp_path / "receipt.json"
    local.write_text(json.dumps(receipt))
    network = tmp_path / "network.json"
    network.write_bytes(NETWORK.read_bytes())
    if which in {"wrong_member_hash", "declared_but_missing"}:
        with pytest.raises((KeyError, ValueError), match="SHA-256|procstat"):
            kmc.adapt(local, "mono", network, root=tmp_path)
        return
    payload, q = kmc.adapt(local, "mono", network, root=tmp_path)
    validate_rate_output_v2(payload)
    assert all(payload["reaction_rates"][0][k] is None for k in ("forward", "reverse", "net"))
    assert all(r["net_production_rate"] is None for r in payload["source_terms"]["species"])
    assert all(r["net_vacancy_rate"] is None for r in payload["source_terms"]["site_inventories"])
    assert q["missing_rate_evidence"] and q["net_species_changes"]["H2-g"] == -7


def test_cell_and_pair_outputs_cannot_silently_exchange_denominators():
    receipt, opts = cat_inputs("phase3_0")
    pair = cat.adapt(receipt, **opts)[0]
    cell = kmc.adapt(MATRIX, "mono", NETWORK, root=ROOT)[0]
    tampered = deepcopy(pair)
    tampered["native_normalization"] = cell["native_normalization"]
    with pytest.raises(ValueError, match="scope"):
        validate_rate_output_v2(tampered)


def test_unknown_reversibility_never_becomes_an_excluded_direction():
    dataset = {"reactions": [{"reaction_id": "unqualified", "direction": {"status": "unknown"}}]}
    with pytest.raises(ValueError, match="Unknown direction model"):
        kmc._observations(dataset, [], None, None)


def test_process_columns_must_be_labeled_and_cumulative():
    with pytest.raises(ValueError, match="header"):
        process_samples(b"configuration 1 0 0\n0 0\n0 0\n")
    with pytest.raises(ValueError, match="counter"):
        process_samples(b"Overall a b\nconfiguration 1 2 1\n0 0 0\n2 2 0\nconfiguration 2 3 2\n0 0 0\n3 1 2\n")


@pytest.mark.parametrize("engine", ["catkinas", "zacros"])
def test_read_only_module_command_and_qualification(engine):
    if engine == "catkinas":
        receipt, opts = cat_inputs("phase3_0")
        args = [sys.executable, "-m", cat.__name__, str(receipt)]
        for key, value in opts.items():
            args += ["--" + key.removesuffix("_path"), str(value)]
        name = "phase3_0"
    else:
        name = "resume"
        args = [sys.executable, "-m", kmc.__name__, str(MATRIX), name, str(NETWORK), "--root", str(ROOT)]
    for extra, expected in (([], json.loads((OUT / "replay" / f"{engine}-{name}.json").read_bytes())),
                            (["--qualification"], json.loads((OUT / f"{engine}_qualification.json").read_bytes())[name])):
        actual = subprocess.run(args + extra, cwd=ROOT, check=True, capture_output=True)
        assert json.loads(actual.stdout) == expected


def test_earlier_smoke_receipt_binds_same_process_and_population_bytes():
    earlier = json.loads((BASE / "phase2_5/native_validation.json").read_bytes())["zacros"]
    with ZipFile(KMC / "benchmarks/continuous.zip") as z:
        for member in ("lattice_output.txt", "procstat_output.txt", "specnum_output.txt"):
            assert sha256_bytes(z.read(member)) == earlier["evidence_sha256"][member]
    assert earlier["events_occurred"] == 20
