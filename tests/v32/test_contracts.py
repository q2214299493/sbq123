from hashlib import sha256
import subprocess
import sys

import pytest
from sbq123.common.artifacts.materialize import materialize
from sbq123.common.evidence.registry import dataset, entry
from sbq123.common.kinetic_model.contracts import Model, identity
from sbq123.common.workflow.process import run_bounded
from sbq123.analysis.observations.reactor import interpret
from sbq123.reactor import simulate


def test_atomic_failure_and_retry(tmp_path):
    dest = tmp_path / "case"
    content = {"one": b"1", "two": b"2"}
    pins = {k: sha256(v).hexdigest() for k, v in content.items()}
    with pytest.raises(ValueError):
        materialize(dest, pins, lambda key: b"1")
    assert {p.name for p in tmp_path.iterdir()} == {".case.sbq123-lock"}
    long = "/".join(["package-subdirectory"] * 16) + "/entry"
    content[long] = b"long"
    pins[long] = sha256(b"long").hexdigest()
    result = materialize(dest, pins, content.__getitem__)
    assert (result / long).read_bytes() == b"long"
    with pytest.raises(FileExistsError):
        materialize(dest, pins, content.__getitem__)


def test_nonfinite_output_never_receives_an_identity():
    for invalid in [float("nan"), float("inf"), -float("inf")]:
        with pytest.raises(ValueError):
            identity({"x": invalid})


def test_archived_mass_action_keeps_qualification_domain():
    m = dataset("v31-closed-cycle")
    assert m.provenance == "archived_software_benchmark" and len(m.steps) == 8
    assert m.temperature_domain_K == (400, 400) and m.pressure_domain_Pa == (160000, 160000)
    with pytest.raises(ValueError, match="domain"):
        m.source([], [], 401, 160000)


def test_result_interpretation_requires_retained_digest():
    out = simulate(
        "PFR",
        dataset_id="zero",
        mode="fixed",
        temperature_K=400,
        pressure_Pa=1e5,
        composition={"A": 1.0, "B": 0.0},
        volume_m3=1.0,
        inlet_mol_s=1, area_m2=1.0,
        reactant="A",
        product="B",
    )
    digest = out["result_sha256"]
    assert interpret(out, digest)["scientific_promotion"] is False
    out["points"][0]["conversion"] = 42
    with pytest.raises(ValueError):
        interpret(out, digest)


def test_process_timeout_cleans_descendant(tmp_path):
    import time

    marker = tmp_path / "after-timeout"
    grandchild = f"import time,pathlib;time.sleep(2);pathlib.Path({str(marker)!r}).write_text('late')"
    code = f"import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',{grandchild!r}]);time.sleep(30)"
    with pytest.raises(subprocess.TimeoutExpired):
        run_bounded([sys.executable, "-c", code], timeout=0.8, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(2.2)
    assert not marker.exists()


def test_local_root_failure_receipts():
    local = pytest.importorskip("sbq123.mkm.catkinas.local")
    model = dataset("langmuir")
    with pytest.raises(local.RootFailure) as failed:
        local.local_point(model, [1, 0], 400, 1e5, [0.5], 0.3, expected_orientation=1)
    assert failed.value.receipt["converged"] is False
    assert "orientation" in failed.value.receipt["reason"]


def test_no_local_solution_returns_no_rates():
    local = pytest.importorskip("sbq123.mkm.catkinas.local")
    raw = entry("datasets", "langmuir")["model"]
    # An empty surface equation has infinitely many roots and cannot qualify one.
    raw["steps"] = []
    model = Model._from_verified_record(raw, registered_digest=identity(raw), provenance="analytical_control")
    with pytest.raises(local.RootFailure, match="singular") as caught:
        local.local_point(model, [1, 0], 400, 1e5, [0.5], 0.3)
    assert not caught.value.receipt["converged"]


def test_stiff_two_time_scales():
    out = simulate(
        "PFR",
        dataset_id="stiff-cascade",
        mode="fixed",
        temperature_K=400,
        pressure_Pa=400 * 8.31446261815324,
        composition={"A": 1, "B": 0, "C": 0},
        volume_m3=1,
        inlet_mol_s=1, area_m2=1,
        reactant="A",
        product="C",
    )
    end = out["points"][-1]["concentration_mol_m3"]
    import math

    b = 10000 / 9999 * (math.exp(-1) - math.exp(-10000))
    assert end == pytest.approx({"A": 0.0, "B": b, "C": 1 - b}, abs=3e-8)


def test_three_local_roots_remain_distinct():
    local = pytest.importorskip("sbq123.mkm.catkinas.local")
    m = dataset("three-surface-roots")
    for root, slope in ((0.2, -1), (0.5, 1), (0.8, -1)):
        _, record = local.local_point(m, [1, 0], 400, 1e5, [root], 0.12)
        assert record["coverage"] == pytest.approx([root], abs=1e-8)
        assert record["orientation"] == slope
    with pytest.raises(local.RootFailure):
        local.local_point(m, [1, 0], 400, 1e5, [0.5], 0.12, expected_orientation=-1)


def test_uniformly_slow_surface_rates_do_not_qualify_the_initial_guess():
    local = pytest.importorskip("sbq123.mkm.catkinas.local")
    data = entry("datasets", "langmuir")["model"]
    for step in data["steps"]:
        step["coefficient"] *= 1e-15
    model = Model._from_verified_record(data, registered_digest=identity(data), provenance="analytical_control")
    _, receipt = local.local_point(model, [1, 0], 400, 1e5, [0.2], 0.5)
    assert receipt["coverage"] == pytest.approx([0.5], abs=1e-8)
    assert max(receipt["equation_scales"]) < 1e-13
