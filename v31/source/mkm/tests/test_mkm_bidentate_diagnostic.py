"""Offline tests of the bounded bidentate route. No MATLAB process is started."""
from copy import deepcopy
from pathlib import Path

import pytest
from scipy.io import savemat

from scripts.baseline_mkm import bidentate_diagnostic as diag
from scripts.baseline_mkm import single_point as point
from scripts.baseline_mkm.mapping_scope import MappingBlocked
from test_mkm_single_point import fixture_ticket, make_decision


def test_only_frozen_diagnostic_can_reach_preflight(tmp_path, monkeypatch):
    design = diag.DESIGN
    contract = point.read(design / "diagnostic-plan.json")
    monkeypatch.setattr(point, "tools_for_run", lambda _: contract["reference_runtime"])
    files = [design / (k + ".json") for k in ("network", "dataset", "configuration")]
    objects = [point.read(p) for p in files]
    hashes = {p.stem: point.sha256_file(p) for p in files}
    with pytest.raises(MappingBlocked):
        point.qualify(*objects)
    altered = deepcopy(objects)
    altered[2]["catkinas"]["initial_coverages"]["H2-bound"] = 0.2
    with pytest.raises(ValueError, match="input differs"):
        diag.qualification(*altered, hashes, None)
    with pytest.raises(ValueError, match="model-reference basis"):
        diag.qualification(*objects, hashes, "unreviewed-profile")

    run = tmp_path / "test-only"
    ticket = fixture_ticket(tmp_path)
    view = point.prepare(run, *files, *ticket, Path("mock"), bidentate_diagnostic=True)
    assert view["stage"] == "AWAITING_APPROVAL"
    decision = tmp_path / "offline-decision.json"
    with pytest.raises(ValueError, match="route differs"):
        point.preflight(run, decision)
    with pytest.raises(FileNotFoundError):
        point.preflight(run, decision, bidentate_diagnostic=True)
    example = make_decision(run, design / "diagnostic-plan.json")
    point.save(decision, example)
    assert point.preflight(run, decision, bidentate_diagnostic=True)[1] == example
    assert not (run / "READY.json").exists()

    stale = tmp_path / "stale.json"
    point.save(stale, dict(example, state_sha256="0" * 64))
    with pytest.raises(ValueError, match="stale"):
        point.preflight(run, stale, bidentate_diagnostic=True)
    with (run / "input/INPUT_phase25.m").open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="differs"):
        point.preflight(run, decision, bidentate_diagnostic=True)


def test_frozen_mat_population_and_flux_criteria(tmp_path):
    frozen = point.read(diag.DESIGN / "diagnostic-plan.json")
    expected = point.read(diag.DESIGN / "analytical-expectations.json")
    binding = dict(case=frozen["case"], expectations=expected, acceptance=frozen["acceptance"])
    eq = expected["equilibrium"]
    result = dict(species=[dict(species_id="H2-bound", molecules_per_reference=eq["molecules_per_site"])],
                  sites=[dict(occupied_fraction=eq["occupied"], vacancy_fraction=eq["vacancies"])],
                  reactions=[dict(forward_flux=eq["forward"], reverse_flux=eq["reverse"], net_flux=0.,
                                  kf=expected["kf_per_bar_s"], kr=expected["kr_per_s"])])
    mat = tmp_path / "control.mat"
    log = "[ y(1), Q1x1_H2 ]\n[ y(2), Q1_v ]\n"
    savemat(mat, dict(yInits=[[0.125, 0.75]]))
    assert diag.validate(binding, result, mat, log)["final"]["occupied"] == eq["occupied"]
    changed = deepcopy(result)
    changed["species"][0]["molecules_per_reference"] = eq["occupied"]
    with pytest.raises(ValueError, match="molecules_per_site"):
        diag.validate(binding, changed, mat, log)
    for key in ("forward_flux", "reverse_flux", "net_flux", "kf", "kr"):
        changed = deepcopy(result)
        changed["reactions"][0][key] += 1
        with pytest.raises(ValueError):
            diag.validate(binding, changed, mat, log)
    savemat(mat, dict(yInits=[[0.25, 0.75]]))
    with pytest.raises(ValueError, match="initial populations differ"):
        diag.validate(binding, result, mat, log)
