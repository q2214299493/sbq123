"""Portable static-start geometry fixtures; no models, DFT, or job execution."""
from __future__ import annotations

import copy
import json
import shutil

import numpy as np
import pytest
from ase import Atoms
from ase.constraints import FixAtoms
from ase.io import read, write

from scripts.artifact_io import sha256_file, sha256_json, source_file_manifest_valid, write_json
from scripts.neb_agent import mz73_static as static, submission
from scripts.registry_schema import migrate_registry
from scripts.ts_strategy_engine.execution_evidence import (
    execution_evidence_sha256, source_bindings_valid, workdir_identity,
)
from scripts.ts_strategy_engine.execution_gate import decide_execution
from tests.test_ts_strategy_engine import contract


LEAF = "paper_chco_aqcat25_ft512_20261112_r000_label"


def save_atoms(path, atoms):
    write(path, atoms, format="vasp", direct=True, sort=False)


def fixture_atoms():
    positions = [[3 + 2.4 * x, 3 + 2.4 * y, 4 + 2.0 * z]
                 for z in range(5) for y in range(3) for x in range(3)]
    positions += [[5.4, 5.4, 14.0], [7.6, 5.4, 14.0], [8.8, 5.4, 14.0], [5.4, 5.4, 15.1]]
    atoms = Atoms(["Fe"] * 45 + ["C", "C", "O", "H"], positions=positions,
                  cell=[20.0, 20.0, 30.0], pbc=True)
    atoms.set_constraint(FixAtoms(indices=range(18)))
    return atoms


def refresh_candidate(scope):
    candidate_sha = sha256_file(scope["workdir"] / "POSCAR")
    scope["paper"]["candidate_structure_sha256"] = candidate_sha
    scope["review"]["candidate_structure_sha256"] = candidate_sha
    write_json(scope["workdir"] / static.PAPER_REQUEST, scope["paper"])
    write_json(scope["arguments"]["review_path"], scope["review"])


def refresh_search_request(scope):
    path = scope["arguments"]["search_request_path"]
    write_json(path, scope["request"])
    scope["arguments"]["search_request_sha256"] = sha256_file(path)


def minimal_preflight(scope):
    return {"experimental_backend": static.BACKEND_ID, "kind": "diagnostic_static",
            "local_workdir_identity": workdir_identity(scope["workdir"]),
            "paper_dft_request": static.validate_paper_dft_request(scope["workdir"]),
            "files": {name: sha256_file(scope["workdir"] / name)
                      for name in ("POSCAR", static.PAPER_REQUEST)}}


def bound_evidence(scope, artifact, name):
    path = scope["workdir"].parent / f"{name}.json"
    write_json(path, artifact)
    return {"preflight": minimal_preflight(scope), name: artifact,
            "source_bindings": {name: {"path": str(path), "sha256": sha256_file(path)}}}


def explicitly_authorized_gate(scope, *, auth_workdir=None):
    """Use real static owners/preflight and explicit file-bound test-only scope."""
    workdir = scope["workdir"]
    backend = static.load_mz73_static_backend(workdir.name)
    (workdir / "INCAR").write_text("NSW=0\nIBRION=-1\nNPAR=1\nNCORE=1\nKPAR=1\n", encoding="ascii")
    (workdir / "KPOINTS").write_text("unit-test-only KPOINTS\n", encoding="ascii")
    (workdir / "POTCAR.spec").write_text("Fe C O H\n", encoding="ascii")
    (workdir / static.LAUNCHER).write_text(static.render_launcher(backend), encoding="ascii", newline="\n")
    database = workdir.parent / "test_only_learning.sqlite3"
    migrate_registry(database)
    preflight = submission.preflight(workdir, "diagnostic_static", learning_database=database,
                                     write_report=False, host=static.BACKEND_ID)
    assert preflight["passed"], preflight["errors"]
    geometry = static.diagnose_static_candidate_geometry(**scope["arguments"])
    analysis = static.analyze_static_candidate_outputs(workdir)
    assert source_file_manifest_valid(geometry) and source_file_manifest_valid(analysis)
    evidence = decide_execution(geometry, analysis, {}, climb=False, path_reviewed=True, preflight=preflight)["EVIDENCE"]
    for name in ("geometry", "analysis", "thresholds", "preflight"):
        path = workdir / ("test_only_" + name + ".json")
        write_json(path, evidence[name])
        evidence["source_bindings"][name] = {"path": str(path), "sha256": sha256_file(path)}
    approval = workdir / "test_only_explicit_authorization.txt"
    approval.write_text("UNIT TEST ONLY: never authorizes a real calculation.", encoding="ascii")
    target = auth_workdir or workdir
    authorization = {
        "schema_version": 1, "document_kind": "user_execution_authorization",
        "action": "SUBMIT_DIAGNOSTIC_VASP", "calculation_kind": "diagnostic_static",
        "authorized_at": "2026-11-12T00:00:00Z",
        "source": {"path": str(approval), "sha256": sha256_file(approval)},
        "target": {"server_alias": static.BACKEND_ID, "remote_dir": backend["remote_root"] + "/" + target.name},
        "workdir_identity": workdir_identity(target), "bundle_sha256": preflight["bundle_sha256"],
        "evidence_sha256": execution_evidence_sha256(evidence),
        "potcar": {"source": "/home/sbq/sbq/test_only/POTCAR", "sha256": "b" * 64,
                   "spec_sha256": preflight["files"]["POTCAR.spec"]},
    }
    path = workdir / "test_only_authorization.json"
    write_json(path, authorization)
    evidence["source_bindings"]["authorization"] = {"path": str(path), "sha256": sha256_file(path)}
    decision = decide_execution(geometry, analysis, {}, climb=False, path_reviewed=True, preflight=preflight,
                                authorization=authorization, source_bindings=evidence["source_bindings"])
    assert decision["EVIDENCE"]["authorization"]["source"]["sha256"] == sha256_file(approval)
    return geometry, decision


@pytest.fixture
def scope(tmp_path, monkeypatch):
    workdir = tmp_path / LEAF
    workdir.mkdir()
    atoms = fixture_atoms()
    save_atoms(workdir / "POSCAR", atoms)
    (workdir / "INCAR").write_text("NSW=0\nIBRION=-1\n", encoding="ascii")
    initial = tmp_path / "original_IS.vasp"
    save_atoms(initial, atoms)
    compatibility = copy.deepcopy(contract()["compatibility"])
    compatibility.update(cell_angstrom=atoms.cell.array.tolist(), fixed_atom_indices_zero_based=list(range(18)), sigma_ev=0.2)
    normalized = contract(reaction_id="test_only_ch_co", reaction_family="co_insertion",
                          atom_map=[[i, i] for i in range(49)], atom_symbols=atoms.get_chemical_symbols(),
                          reaction_atoms=[45, 46, 47, 48], broken_bonds=[], formed_bonds=[[45, 46]],
                          site_changes=[], compatibility=compatibility)
    # Main-work contracts retain this extension. Register only this fixture's
    # exact identities in the scoped bridge; the production config is untouched.
    normalized["compatibility"]["cell_angstrom"] = atoms.cell.array.tolist()
    normalized["compatibility_sha256"] = sha256_json(normalized["compatibility"])
    normalized.pop("contract_sha256")
    normalized["contract_sha256"] = sha256_json(normalized)
    registered_caps = {key: normalized[key] for key in
                       ("contract_sha256", "compatibility_sha256", "atom_map_sha256")}
    real_loader = static.load_mz73_static_backend

    def fixture_backend(*args, **kwargs):
        backend = copy.deepcopy(real_loader(*args, **kwargs))
        backend["reviewed_contract"] = copy.deepcopy(registered_caps)
        return backend

    monkeypatch.setattr(static, "load_mz73_static_backend", fixture_backend)
    contract_path = tmp_path / "reaction_contract.json"
    write_json(contract_path, normalized)
    guards = {"minimum_pair_distance_A": 0.65, "preserved_bonds": [
        {"name": "CH_retained", "atoms_zero_based": [45, 48], "minimum_A": 0.95,
         "maximum_A": 1.25, "hard_minimum_A": 0.65, "hard_maximum_A": 1.8},
        {"name": "CO_retained", "atoms_zero_based": [46, 47], "minimum_A": 1.05,
         "maximum_A": 1.65, "hard_minimum_A": 0.8, "hard_maximum_A": 2.3}]}
    guard_path = tmp_path / "reviewed_geometry_guards.json"
    write_json(guard_path, {"geometry_guards": guards})
    request = {"initial": {"path": str(initial), "sha256": sha256_file(initial)},
               "checkpoint": {"sha256": "c" * 64}, "fixed_indices_zero_based": list(range(18)),
               "reaction": {**{key: normalized[key] for key in
                               ("contract_sha256", "compatibility_sha256", "atom_map_sha256")},
                            "bonds": [[45, 46, "form"]], "monitor_pairs": {"CH": [45, 48], "CO": [46, 47]}},
               "geometry_guard_source": {"path": str(guard_path), "sha256": sha256_file(guard_path)},
               "geometry": {"minimum_pair_distance_A": 0.65, "preserved_bonds": [
                   {"name": row["name"], "atoms": row["atoms_zero_based"], "minimum_A": row["hard_minimum_A"],
                    "maximum_A": row["hard_maximum_A"], "soft_minimum_A": row["minimum_A"],
                    "soft_maximum_A": row["maximum_A"]} for row in guards["preserved_bonds"]]}}
    search_path = tmp_path / "search_request.json"
    write_json(search_path, request)
    geometry_path = tmp_path / "test_only_review_geometry.json"
    geometry_path.write_bytes(b'{"test_only": true, "not_scientific_result": true}\n')
    image_path = tmp_path / "test_only_review_image.png"
    image_path.write_bytes(b"test-only placeholder image bytes, never a scientific review image")
    review_path = tmp_path / "candidate_review.json"
    review = {"reviewer": "unit-test fixture only", "decision": "accepted_for_exact_structure_DFT_force_diagnosis_only",
              "candidate_structure_sha256": sha256_file(workdir / "POSCAR"),
              "geometry_evidence_sha256": sha256_file(geometry_path), "image_sha256": sha256_file(image_path),
              "not_transition_state_acceptance": True}
    write_json(review_path, review)
    paper = {"document_kind": "paper_sequential_DFT_request", "calculation": "exact_structure_static_single_point",
             "requires_exact_structure_hash_gate": True, "requires_authoritative_execution_gate": True,
             "protocol_sha256": "a" * 64, "candidate_structure_sha256": sha256_file(workdir / "POSCAR"),
             "search_checkpoint_sha256": request["checkpoint"]["sha256"],
             **{key: normalized[key] for key in ("contract_sha256", "compatibility_sha256")}}
    write_json(workdir / static.PAPER_REQUEST, paper)
    return {"workdir": workdir, "request": request, "paper": paper, "review": review,
            "registered_caps": registered_caps,
            "arguments": {"workdir": workdir, "initial_structure_path": initial,
                          "search_request_path": search_path, "search_request_sha256": sha256_file(search_path),
                          "contract_path": contract_path, "review_path": review_path,
                          "geometry_evidence_path": geometry_path, "review_image_path": image_path}}


def test_real_49_atom_static_geometry_and_no_output_are_bound(scope):
    geometry = static.diagnose_static_candidate_geometry(**scope["arguments"])
    assert geometry["status"] == "PASS" and geometry["hard_errors"] == []
    assert geometry["atom_count"] == 49 and geometry["fixed_atom_indices_zero_based"] == list(range(18))
    assert geometry["minimum_pair_distance_A"] >= 0.65
    assert geometry["not_transition_state_acceptance"] and not geometry["submission_allowed"]
    assert {row["name"] for row in geometry["preserved_bonds"]} == {"CH_retained", "CO_retained"}
    preflight = minimal_preflight(scope)
    assert static.validate_static_evidence(geometry, preflight, name="geometry")
    analysis = static.analyze_static_candidate_outputs(scope["workdir"])
    assert analysis["status"] == "NO_OUTPUT" and analysis["outputs_present"] == []
    assert "images" not in analysis and not analysis["scientifically_validated_ts"]
    assert static.validate_static_evidence(analysis, preflight, name="analysis")
    assert source_bindings_valid(bound_evidence(scope, geometry, "geometry"), ("geometry",))
    assert source_bindings_valid(bound_evidence(scope, analysis, "analysis"), ("analysis",))


@pytest.mark.parametrize("change", ["missing_poscar", "cell", "mask", "species", "fixed_position", "nonfinite"])
def test_actual_candidate_identity_failures_are_rejected(scope, change):
    path = scope["workdir"] / "POSCAR"
    if change == "missing_poscar":
        path.unlink()
    else:
        atoms = read(path, format="vasp")
        if change == "cell":
            atoms.set_cell([21.0, 20.0, 30.0])
        elif change == "mask":
            atoms.set_constraint(FixAtoms(indices=range(17)))
        elif change == "species":
            atoms[48].symbol = "C"
        elif change == "fixed_position":
            atoms.positions[0, 0] += 0.1
        else:
            atoms.positions[45, 0] = np.nan
        save_atoms(path, atoms)
        refresh_candidate(scope)
    with pytest.raises((OSError, ValueError)):
        static.diagnose_static_candidate_geometry(**scope["arguments"])


@pytest.mark.parametrize("change", ["request_sha", "initial_sha", "contract_sha", "guard_sha", "guard_bounds", "minimum_contact"])
def test_original_input_contract_and_reviewed_guards_must_match(scope, change):
    if change == "request_sha":
        scope["arguments"]["search_request_sha256"] = "0" * 64
    else:
        if change == "initial_sha":
            scope["request"]["initial"]["sha256"] = "0" * 64
        elif change == "contract_sha":
            scope["request"]["reaction"]["contract_sha256"] = "0" * 64
        elif change == "guard_sha":
            scope["request"]["geometry_guard_source"]["sha256"] = "0" * 64
        elif change == "guard_bounds":
            scope["request"]["geometry"]["preserved_bonds"][0]["maximum_A"] = 8.0
        else:
            scope["request"]["geometry"]["minimum_pair_distance_A"] = 0.01
        refresh_search_request(scope)
    with pytest.raises(ValueError):
        static.diagnose_static_candidate_geometry(**scope["arguments"])


@pytest.mark.parametrize("identity", ["contract_sha256", "compatibility_sha256", "atom_map_sha256"])
def test_contract_must_match_the_registered_case_caps(scope, identity):
    scope["registered_caps"][identity] = "0" * 64
    with pytest.raises(ValueError):
        static.diagnose_static_candidate_geometry(**scope["arguments"])


@pytest.mark.parametrize("rehash", [False, True])
def test_modified_or_other_logical_contract_cannot_enter_the_fixed_bridge(scope, rehash):
    path = scope["arguments"]["contract_path"]
    value = json.loads(path.read_text(encoding="utf-8"))
    value["reaction_id"] = "unregistered_other_reaction"
    if rehash:
        value.pop("contract_sha256")
        value["contract_sha256"] = sha256_json(value)
    write_json(path, value)
    with pytest.raises(ValueError):
        static.diagnose_static_candidate_geometry(**scope["arguments"])


@pytest.mark.parametrize("field,value", [
    ("reviewer", ""), ("decision", "accepted_transition_state"),
    ("not_transition_state_acceptance", False), ("candidate_structure_sha256", "0" * 64),
    ("geometry_evidence_sha256", "0" * 64), ("image_sha256", "0" * 64),
])
def test_actual_candidate_review_must_bind_all_three_artifacts(scope, field, value):
    scope["review"][field] = value
    write_json(scope["arguments"]["review_path"], scope["review"])
    with pytest.raises(ValueError, match="work review"):
        static.diagnose_static_candidate_geometry(**scope["arguments"])


@pytest.mark.parametrize("change", ["reaction_bond", "retained_pair", "fixed_mask"])
def test_source_reaction_atom_roles_cannot_be_substituted(scope, change):
    if change == "reaction_bond":
        scope["request"]["reaction"]["bonds"] = [[46, 47, "form"]]
    elif change == "retained_pair":
        scope["request"]["reaction"]["monitor_pairs"]["CH"] = [46, 47]
    else:
        scope["request"]["fixed_indices_zero_based"] = list(range(17))
    refresh_search_request(scope)
    with pytest.raises(ValueError):
        static.diagnose_static_candidate_geometry(**scope["arguments"])


@pytest.mark.parametrize("change,error", [("CH", "retained_bond:CH_retained"),
                                         ("CO", "retained_bond:CO_retained"),
                                         ("collision", "minimum_pair_distance")])
def test_real_hard_bond_or_contact_failures_are_reported(scope, change, error):
    path = scope["workdir"] / "POSCAR"
    atoms = read(path, format="vasp")
    if change == "CH":
        atoms.positions[48] = atoms.positions[45] + [0, 0, 2.0]
    elif change == "CO":
        atoms.positions[47] = atoms.positions[46] + [2.8, 0, 0]
    else:
        atoms.positions[44] = atoms.positions[45] + [0.2, 0, 0]
    save_atoms(path, atoms)
    refresh_candidate(scope)
    evidence = static.diagnose_static_candidate_geometry(**scope["arguments"])
    assert evidence["status"] == "FAIL" and error in evidence["hard_errors"]


def test_soft_bond_warning_does_not_hide_hard_gate_or_accept_a_ts(scope):
    path = scope["workdir"] / "POSCAR"
    atoms = read(path, format="vasp")
    atoms.positions[48] = atoms.positions[45] + [0, 0, 1.4]
    save_atoms(path, atoms)
    refresh_candidate(scope)
    evidence = static.diagnose_static_candidate_geometry(**scope["arguments"])
    assert evidence["status"] == "PASS" and evidence["warnings"] == ["retained_bond_soft_window:CH_retained"]
    assert evidence["not_transition_state_acceptance"]


@pytest.mark.parametrize("field,value", [("experimental_backend", "sunboquan-codex"),
                                       ("experimental_backend", None), ("kind", "ordinary_neb")])
def test_static_artifacts_cannot_change_lsf_or_neb_authority(scope, field, value):
    artifact = static.diagnose_static_candidate_geometry(**scope["arguments"])
    preflight = minimal_preflight(scope)
    preflight[field] = value
    assert not static.validate_static_evidence(artifact, preflight, name="geometry")
    evidence = bound_evidence(scope, artifact, "geometry")
    evidence["preflight"] = preflight
    assert not source_bindings_valid(evidence, ("geometry",))


@pytest.mark.parametrize("field,value", [("producer", "invented_parser"),
                                       ("document_kind", "neb_geometry_diagnosis")])
def test_wrong_artifact_owner_is_rejected(scope, field, value):
    artifact = static.diagnose_static_candidate_geometry(**scope["arguments"])
    artifact[field] = value
    assert not static.validate_static_evidence(artifact, minimal_preflight(scope), name="geometry")


@pytest.mark.parametrize("output", ["OUTCAR", "OSZICAR", "vasp.out"])
def test_real_outputs_invalidate_cached_no_output_analysis(scope, output):
    artifact = static.analyze_static_candidate_outputs(scope["workdir"])
    evidence = bound_evidence(scope, artifact, "analysis")
    (scope["workdir"] / output).write_bytes(b"unit-test output-presence marker only\n")
    actual = static.analyze_static_candidate_outputs(scope["workdir"])
    assert actual["status"] == "OUTPUT_PRESENT" and actual["outputs_present"] == [output]
    assert not static.validate_static_evidence(artifact, minimal_preflight(scope), name="analysis")
    assert not source_bindings_valid(evidence, ("analysis",))


@pytest.mark.parametrize("source", ["search_request_path", "geometry_evidence_path", "review_image_path", "review_path"])
def test_changed_original_sources_invalidate_cached_geometry(scope, source):
    artifact = static.diagnose_static_candidate_geometry(**scope["arguments"])
    preflight = minimal_preflight(scope)
    path = scope["arguments"][source]
    path.write_bytes(path.read_bytes() + b"\n")
    assert not static.validate_static_evidence(artifact, preflight, name="geometry")


def test_dft_request_and_preflight_poscar_binding_cannot_be_substituted(scope):
    artifact = static.diagnose_static_candidate_geometry(**scope["arguments"])
    preflight = minimal_preflight(scope)
    preflight["files"]["POSCAR"] = "0" * 64
    assert not static.validate_static_evidence(artifact, preflight, name="geometry")
    preflight = minimal_preflight(scope)
    preflight["files"][static.PAPER_REQUEST] = "0" * 64
    assert not static.validate_static_evidence(artifact, preflight, name="geometry")


@pytest.mark.parametrize("hard_failure", [False, True], ids=["real-PASS-explicit-auth", "real-FAIL-explicit-auth"])
def test_real_static_geometry_controls_canonical_gate_even_with_explicit_authorization(scope, hard_failure):
    if hard_failure:
        path = scope["workdir"] / "POSCAR"
        atoms = read(path, format="vasp")
        atoms.positions[48] = atoms.positions[45] + [0, 0, 2.0]
        save_atoms(path, atoms)
        refresh_candidate(scope)
    geometry, decision = explicitly_authorized_gate(scope)
    assert source_file_manifest_valid(geometry)
    assert geometry["status"] == ("FAIL" if hard_failure else "PASS")
    assert decision["ALLOWED_ACTIONS"] == ([] if hard_failure else ["SUBMIT_DIAGNOSTIC_VASP"])
    assert not decision["TS_CLAIM_ALLOWED"]


def test_other_leaf_no_output_cannot_replace_current_leaf_with_real_outcar(scope, monkeypatch):
    import yaml
    from scripts.neb_agent.mz73_timebudget import TIMEOUT_LEAF

    # Preserve this original same-bytes/different-directory regression under
    # its historical 30-minute config. New r001 budget requirements have their
    # own tests; no production validation or authorization is bypassed here.
    historical = yaml.safe_load(static.DEFAULT_CONFIG.read_text(encoding="utf-8"))
    configured = historical["backends"][static.BACKEND_ID]
    configured.pop("time_budget_extension")
    configured["allowed_workdir_names"].remove(TIMEOUT_LEAF)
    config_path = scope["workdir"].parent / "historical_30min_backend.yaml"
    config_path.write_text(yaml.safe_dump(historical), encoding="utf-8")
    real_loader = static.load_mz73_static_backend
    monkeypatch.setattr(static, "load_mz73_static_backend",
                        lambda *a, **k: real_loader(*a, **{**k, "config_path": config_path}))
    other = scope["workdir"].with_name(LEAF.replace("r000", "r001"))
    other.mkdir()
    for name in ("POSCAR", "INCAR", static.PAPER_REQUEST):
        shutil.copyfile(scope["workdir"] / name, other / name)
    preflight0 = minimal_preflight(scope)
    (scope["workdir"] / "OUTCAR").write_bytes(b"unit-test output marker; never DFT evidence\n")
    actual_other = static.analyze_static_candidate_outputs(other)
    actual_current = static.analyze_static_candidate_outputs(scope["workdir"])
    assert actual_other["status"] == "NO_OUTPUT" and actual_current["status"] == "OUTPUT_PRESENT"
    assert source_file_manifest_valid(actual_other)
    assert not static.validate_static_evidence(actual_other, preflight0, name="analysis")
    evidence = bound_evidence(scope, actual_other, "analysis")
    assert evidence["preflight"]["local_workdir_identity"] == workdir_identity(scope["workdir"])
    assert not source_bindings_valid(evidence, ("analysis",))


def test_valid_whole_source_set_cannot_be_reused_with_other_leaf_authorization(scope):
    other = scope["workdir"].with_name(LEAF.replace("r000", "r001"))
    other.mkdir()
    geometry, decision = explicitly_authorized_gate(scope, auth_workdir=other)
    assert geometry["status"] == "PASS" and source_file_manifest_valid(geometry)
    assert decision["EVIDENCE"]["authorization"]["workdir_identity"] == workdir_identity(other)
    assert decision["EVIDENCE"]["preflight"]["local_workdir_identity"] == workdir_identity(scope["workdir"])
    assert decision["ALLOWED_ACTIONS"] == []
