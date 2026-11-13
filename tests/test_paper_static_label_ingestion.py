"""Mock-only glue checks: placeholder OUTCARs are never parsed as DFT results."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from scripts.artifact_io import sha256_bytes, sha256_file, write_json_exclusive
from scripts.matris_training_exclusions import geometry_fingerprint
from scripts.neb_agent.utils_structure import Poscar
from scripts.ts_strategy_engine.paper_sequential import (
    accept_force_label, create_protocol, initialize_state, prepare_dft_evaluation, record_execution,
)


SOURCE = Path(__file__).resolve().parents[1] / "archive/chco_paper_aqcat25_20261112/ingest_static_label.py"
spec = importlib.util.spec_from_file_location("paper_static_label_glue", SOURCE)
glue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(glue)


@pytest.fixture
def mocked_case(tmp_path, monkeypatch):
    import ase.io
    from pymatgen.io.vasp.inputs import Kpoints
    from scripts import aqcat25_calibration, vasp_result_gate
    from scripts.neb_agent import submission, utils_structure, utils_vasp

    directory = tmp_path / "paper_chco_aqcat25_ft512_20261112_r000_label"
    directory.mkdir()
    for name in ("POSCAR", "INCAR", "KPOINTS", "POTCAR", "POTCAR.spec", "OUTCAR", "OSZICAR", "CONTCAR", "script.sbatch"):
        (directory / name).write_text("MOCK ONLY: " + name)
    structure = Poscar("mock", np.eye(3) * 20, ["Fe", "C", "O", "H"], [45, 2, 1, 1],
                       np.arange(147, dtype=float).reshape(49, 3) / 1000, True,
                       [("F", "F", "F")] * 18 + [("T", "T", "T")] * 31)
    protocol = create_protocol(initial_checkpoint_path="/home/sbq/sbq/frozen.pt", initial_checkpoint_sha256="a" * 64,
                               contract_sha256="c" * 64, compatibility_sha256="d" * 64, atom_count=49,
                               movable_atom_indices=list(range(18, 49)), formed_bonds_1based=[[46, 47]],
                               broken_bonds_1based=[], maximum_dft_evaluations=2, model_adaptation="mock AQCat",
                               dft_adaptation="mock Slurm VASP")
    candidate = sha256_file(directory / "POSCAR")

    def state_for(settings):
        state = prepare_dft_evaluation(initialize_state(settings), candidate_structure_sha256=candidate, search_checkpoint_sha256="a" * 64)
        return record_execution(state, job_id="101", bundle_sha256="b" * 64, gate_sha256="e" * 64)

    state = state_for(protocol)
    state_path = tmp_path / "state.json"
    write_json_exclusive(state_path, state)
    files = {name: sha256_file(directory / name) for name in ("POSCAR", "INCAR", "KPOINTS", "POTCAR.spec", "script.sbatch")}
    write_json_exclusive(directory / "submission_preflight.json", {"experimental_backend": "mz73_paper_vasp"})
    write_json_exclusive(directory / "submission_record.json", {
        "status": "SUBMITTED", "scheduler": "Slurm", "server_alias": "mz73_paper_vasp", "job_id": "101",
        "bundle_sha256": "b" * 64, "gate_decision_sha256": "e" * 64,
        "potcar_sha256": sha256_file(directory / "POTCAR"), "remote_dir": "/home/sbq/sbq/mock/" + directory.name})
    bundle = SimpleNamespace(kind="diagnostic_static", bundle_sha256="b" * 64, files=tuple(files.items()), verify=lambda path: None)
    monkeypatch.setattr(submission.InputBundle, "from_preflight", classmethod(lambda cls, report: bundle))
    compatibility = {"potcar_bundle_sha256": sha256_file(directory / "POTCAR"), "encut_ev": 400.0, "ediff_ev": 1e-5,
                     "ismear": 1, "sigma_ev": 0.2, "kmesh": [5, 5, 1], "fixed_atom_indices_zero_based": list(range(18)),
                     "cell_angstrom": structure.cell.tolist()}
    contract = {"reaction_id": "MOCK_ONLY", "contract_sha256": "c" * 64, "compatibility_sha256": "d" * 64,
                "compatibility": compatibility, "atom_symbols": structure.labels}
    contract_path = tmp_path / "contract.json"
    contract_path.write_text("MOCK OWNER CONTRACT")
    contract_calls = []
    contract_bridge = ModuleType("scripts.neb_agent.mz73_static")

    def load_contract(path, **kwargs):
        contract_calls.append((path, kwargs))
        return contract

    contract_bridge.load_reviewed_case_contract = load_contract
    monkeypatch.setitem(sys.modules, "scripts.neb_agent.mz73_static", contract_bridge)
    monkeypatch.setattr(utils_structure, "read_poscar", lambda path: structure)
    monkeypatch.setattr(vasp_result_gate, "read_incar_values", lambda path: {
        "NSW": "0", "IBRION": "-1", "ISPIN": "2", "ENCUT": "400", "EDIFF": "1e-6", "ISMEAR": "1", "SIGMA": ".2"})
    monkeypatch.setattr(Kpoints, "from_file", classmethod(lambda cls, path: SimpleNamespace(kpts=[(5, 5, 1)], style="Gamma", kpts_shift=(0, 0, 0))))
    parsed = {"normal_completion": True, "final_toten_eV": -50.0, "forces_eV_per_A": [[0.2, 0.0, 0.0]] * 49,
              "positions_A": (structure.frac @ structure.cell).tolist(), "cell_A": structure.cell.tolist(),
              "symbols": structure.labels}
    scf = {"electronically_converged": True, "last_electronic_iteration": 10, "nelm": 100,
           "last_delta_e_eV": 1e-7, "ediff_eV": 1e-6, "electronic_convergence_source": "OSZICAR_DELTA_E"}
    magnetic = {"normal_completion": True, "fatal_keywords": [], "run_index": 1,
                "local_magnetization_last_muB": [2.0] * 45 + [0.0] * 4, "total_magnetization_history_muB": [90.0]}
    monkeypatch.setattr(aqcat25_calibration, "parse_final_outcar", lambda path, **kwargs: parsed)
    monkeypatch.setattr(vasp_result_gate, "final_scf_status", lambda *paths: scf)
    monkeypatch.setattr(utils_vasp, "parse_outcar", lambda path: magnetic)
    output = SimpleNamespace(cell=structure.cell.copy(), positions=structure.frac @ structure.cell,
                             get_chemical_symbols=lambda: structure.labels,
                             get_forces=lambda apply_constraint: np.asarray(parsed["forces_eV_per_A"]))
    monkeypatch.setattr(ase.io, "read", lambda *args, **kwargs: output)
    scheduler = tmp_path / "scheduler.json"
    write_json_exclusive(scheduler, {"job_id": "101", "scheduler": "Slurm", "job_state": "COMPLETED"})
    live_calls = []
    slurm = ModuleType("scripts.slurm_force_label")

    def live(evidence, **kwargs):
        live_calls.append(kwargs)
        return {"MOCK_ONLY": True, "job_id": "101", "job_state": "COMPLETED", "exit_code": "0:0"}

    slurm.verify_slurm_force_label_live = live
    monkeypatch.setitem(sys.modules, "scripts.slurm_force_label", slurm)
    backend = Path(__file__).resolve().parents[1] / "configs/execution_backends.yaml"
    args = SimpleNamespace(directory=directory, state=state_path, state_sha256=sha256_file(state_path),
                           contract=contract_path, scheduler_evidence=scheduler, backend_config=backend)
    return SimpleNamespace(args=args, state=state, protocol=protocol, state_for=state_for, structure=structure,
                           parsed=parsed, scf=scf, magnetic=magnetic, output=output, live_calls=live_calls, slurm=slurm,
                           contract_calls=contract_calls)


def test_mock_only_valid_label_keeps_raw_forces_and_can_enter_paper_review(mocked_case):
    case = mocked_case
    standard, paper = glue.review(case.args)
    assert standard["document_kind"] == "vasp_ts_force_label" and standard["forces_eV_per_A"][0] == [0.2, 0, 0]
    assert paper["geometry_sha256"] == geometry_fingerprint(case.structure)
    assert paper["scheduler_evidence"]["job_id"] == "101" and len(case.live_calls) == 1
    assert case.live_calls[0]["config_path"] == case.args.backend_config
    assert case.contract_calls == [(case.args.contract, {"workdir_name": case.args.directory.name,
                                                        "config_path": case.args.backend_config})]
    assert paper["scheduler_evidence"]["source_files"]["script.sbatch"]["sha256"] == sha256_file(case.args.directory / "script.sbatch")
    raw = json.dumps(paper).encode()
    updated = accept_force_label(case.state, raw, expected_sha256=sha256_bytes(raw))
    assert updated["status"] == "awaiting_training_request"
    assert sha256_file(case.args.state) == case.args.state_sha256


@pytest.mark.parametrize("failure", ["scf", "scf_at_limit", "normal", "magnetic", "total_magnetic_missing",
                                     "force_shape", "evaluated_geometry", "potcar", "input_hash", "live", "source_changed"])
def test_mock_scientific_or_live_failure_cannot_produce_label(mocked_case, failure):
    case = mocked_case
    if failure == "scf":
        case.scf["electronically_converged"] = False
    elif failure == "scf_at_limit":
        case.scf["last_electronic_iteration"] = case.scf["nelm"]
    elif failure == "normal":
        case.parsed["normal_completion"] = False
    elif failure == "magnetic":
        case.magnetic["local_magnetization_last_muB"] = [2.0] * 48
    elif failure == "total_magnetic_missing":
        case.magnetic["total_magnetization_history_muB"] = []
    elif failure == "force_shape":
        case.parsed["forces_eV_per_A"] = [[0.0] * 3] * 48
    elif failure == "evaluated_geometry":
        case.output.positions = case.output.positions + 0.01
    elif failure == "potcar":
        (case.args.directory / "POTCAR").write_text("CHANGED MOCK BUNDLE")
    elif failure == "input_hash":
        (case.args.directory / "POSCAR").write_text("CHANGED MOCK INPUT")
    elif failure == "live":
        case.slurm.verify_slurm_force_label_live = lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("MOCK nonterminal live job"))
    else:
        def change_source(*args, **kwargs):
            (case.args.directory / "OUTCAR").write_text("CHANGED MOCK OUTPUT")
            return {"MOCK_ONLY": True}
        case.slurm.verify_slurm_force_label_live = change_source
    with pytest.raises(ValueError):
        glue.review(case.args)


def test_protected_geometry_is_rejected_before_live_query(mocked_case):
    case = mocked_case
    case.protocol["held_out_geometry_sha256"] = [geometry_fingerprint(case.structure)]
    state = case.state_for(case.protocol)
    case.args.state = case.args.state.with_name("protected_state.json")
    write_json_exclusive(case.args.state, state)
    case.args.state_sha256 = sha256_file(case.args.state)
    with pytest.raises(ValueError, match="protected"):
        glue.review(case.args)
    assert not case.live_calls


def test_execution_receipt_must_exist_before_ingestion(mocked_case):
    case = mocked_case
    state = prepare_dft_evaluation(initialize_state(case.protocol),
                                   candidate_structure_sha256=sha256_file(case.args.directory / "POSCAR"),
                                   search_checkpoint_sha256="a" * 64)
    case.args.state = case.args.state.with_name("not_executed_state.json")
    write_json_exclusive(case.args.state, state)
    case.args.state_sha256 = sha256_file(case.args.state)
    with pytest.raises(ValueError, match="record_execution"):
        glue.review(case.args)
    assert not case.live_calls


@pytest.mark.parametrize('ediff', ['1e-5', '1e-7', '0', 'nan'])
def test_only_approved_force_label_stage_precision_can_enter_training(mocked_case, monkeypatch, ediff):
    from scripts import vasp_result_gate

    original = vasp_result_gate.read_incar_values
    monkeypatch.setattr(vasp_result_gate, 'read_incar_values', lambda path: {**original(path), 'EDIFF': ediff})
    with pytest.raises(ValueError, match='compatibility mismatch'):
        glue.review(mocked_case.args)
    assert not mocked_case.live_calls
