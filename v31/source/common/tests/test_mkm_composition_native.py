"""Offline replay of accepted constrained-composition pairs from their native outputs."""

from decimal import Decimal

import numpy as np
import pytest

from scripts.artifact_io import load_json_object as read, sha256_file, sha256_json
from scripts.baseline_mkm.drc_pair import REPORTS
from scripts.baseline_mkm.results import read_single_point


@pytest.mark.parametrize("size", ["coarse", "fine"])
def test_native_constrained_order_from_hno_production(size):
    reference = REPORTS / "phase3_0"
    output = REPORTS / "phase3_2_2_1"
    baseline = read_single_point(reference / "data1.mat", reference / "native_log_extract.txt")
    row = read(output / "result.json")["pairs"][size]
    no = [baseline["partial_pressures_bar"]["P_NO"]]
    tof = [baseline["net_gas_flux_per_reference_site_s"]["HNO"] / 2]
    for side in ("minus", "plus"):
        member = output / size / side
        receipt = read(member / "accepted.json")
        plan = read(member / "plan.json")
        decision = read(member / "approval.json")
        assert sha256_json(plan) == decision["state_sha256"]
        assert sha256_json(decision) == receipt["approval_reference"]
        assert sha256_file(member / "data1.mat") == receipt["output_hashes"]["runtime/result_phase25/data1.mat"]
        raw = read_single_point(member / "data1.mat", member / "native_log_extract.txt")
        gases = raw["partial_pressures_bar"]
        exact = {k: Decimal(str(v)) for k, v in gases.items()}
        assert sum(exact.values()) == Decimal("1.600000")
        assert exact["P_H2"] == 10 * exact["P_HNO"]
        assert {k.removeprefix("P_") + "-g": v for k, v in gases.items()} == plan["partial_pressures_bar"]
        no.append(gases["P_NO"])
        tof.append(raw["net_gas_flux_per_reference_site_s"]["HNO"] / 2)
        assert tof[-1] == pytest.approx(row["cases"][side]["net_tof_per_site_pair_s"], rel=1e-10)
    x = np.log(np.asarray(no) / no[0])
    assert x[1] < 0 < x[2]
    _, slope, _ = np.linalg.solve(np.vander(x, 3, increasing=True), np.log(tof))
    assert slope == pytest.approx(row["estimates"]["quadratic_at_zero"], abs=1e-11)
