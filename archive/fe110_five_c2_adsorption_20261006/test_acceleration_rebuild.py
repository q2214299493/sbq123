import copy
import hashlib
import json

import pytest

from archive.fe110_five_c2_adsorption_20261006.collect_adsorption_acceleration_frames import REMOTE_READER, selected_steps
from scripts.adsorption.acceleration_benchmark import compare_costs


def runs():
    baseline = {"normal_completion": True, "electronic_converged": True, "force_converged": True,
                "geometry_accepted": True, "original_seed_sha256": "a" * 64,
                "compatibility_sha256": "b" * 64, "resource_signature": "sameCPU32",
                "reviewed_minimum_id": "same_minimum", "vasp_elapsed_seconds": 1000, "ionic_steps": 200}
    accelerated = copy.deepcopy(baseline)
    accelerated.update(vasp_elapsed_seconds=200, ionic_steps=40)
    return baseline, accelerated


def test_count_overheads_not_just_steps():
    result = compare_costs(*runs(), gpu_seconds=50, shared_training_and_label_seconds=900, amortization_tasks=10)
    assert result["vasp_step_ratio"] == 5
    assert result["first_case_cost_reduced"] is False
    assert result["amortized_cost_reduced"] is True
    assert result["cases_until_shared_cost_recovered"] == 2


@pytest.mark.parametrize("field", ["force_converged", "reviewed_minimum_id", "compatibility_sha256", "resource_signature"])
def test_unfair_comparisons_rejected(field):
    baseline, accelerated = runs()
    accelerated[field] = False if field == "force_converged" else "different"
    with pytest.raises(ValueError):
        compare_costs(baseline, accelerated, 0)


def test_no_recurring_saving_no_break_even():
    baseline, accelerated = runs()
    accelerated["vasp_elapsed_seconds"] = 1100
    assert compare_costs(baseline, accelerated, 1)["cases_until_shared_cost_recovered"] is None


def test_bounded_deterministic_frame_selection():
    assert selected_steps(218) == [1, 2, 5, 54, 109, 164, 217, 218]
    assert len(selected_steps(5)) <= 5


def test_remote_reader_energy_frame_and_source_hash(tmp_path, capsys):
    for filename in ("POSCAR", "CONTCAR", "INCAR", "KPOINTS", "OSZICAR", "XDATCAR"):
        (tmp_path / filename).write_text("synthetic test input\n")
    body = []
    for step in range(1, 6):
        body.extend([f"Iteration {step}( 3)\n", "aborting loop because EDIFF is reached\n",
                     "TOTAL-FORCE (eV/Angst)\n", "-----------------------\n"])
        body.extend(["0.00000 0.00000 0.00000 0.0 0.0 0.0\n"] * 48)
        body.extend(["-----------------------\n", f"free  energy   TOTEN  = {-step:.8f} eV\n"])
    body.extend(["reached required accuracy\n", "General timing and accounting informations\n"])
    path = tmp_path / "OUTCAR"
    path.write_text("".join(body))
    exec(REMOTE_READER, {"RECORDS": [{"name": "synthetic", "remote_dir": str(tmp_path)}],
                         "selected_steps": selected_steps})
    result = json.loads(capsys.readouterr().out)
    assert result["OUTCAR_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert [f["toten_eV"] for f in result["frames"]] == [-1, -2, -4, -5]
    assert all(f["EDIFF_marker_before_force"] for f in result["frames"])
