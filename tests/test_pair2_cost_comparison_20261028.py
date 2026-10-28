"""Acceptance must reflect valid DFT convergence rather than a small ML force."""
import importlib

import pytest

from archive.fe110_pair2_cost_comparison_20261028.analyze import threshold_work
from archive.fe110_pair2_cost_comparison_20261028.collect import reader
from archive.fe110_pair2_cost_comparison_20261028.recover import decode


def frame(step, force, scf=True, magnetic=True):
    return {"ionic_step": step, "DFT_movable_fmax_eV_A": force,
        "SCF_pass": scf, "magnetic_review_pass": magnetic, "cumulative_SCF_iterations": step * 10}


@pytest.mark.parametrize("module", ["collect", "recover", "resume", "analyze"])
def test_entrypoints_import_without_remote_execution(module):
    assert importlib.import_module("archive.fe110_pair2_cost_comparison_20261028." + module)


def test_unreached_target_has_no_completion_step_or_zero_cost():
    result = threshold_work([frame(1, .09), frame(2, .021)], .02)
    assert result["first_valid_crossing_step"] is None
    assert result["cumulative_SCF_iterations_at_crossing"] is None
    assert result["minimum_valid_fmax_eV_A"] == .021


@pytest.mark.parametrize("scf,magnetic", [(False, True), (True, False)])
def test_invalid_electronic_or_magnetic_frame_cannot_establish_crossing(scf, magnetic):
    result = threshold_work([frame(1, .01, scf, magnetic), frame(2, .018)], .02)
    assert result["first_valid_crossing_step"] == 2
    assert result["cumulative_SCF_iterations_at_crossing"] == 20


def test_transient_force_crossing_does_not_imply_official_completion():
    result = threshold_work([frame(1, .019), frame(2, .10)], .02)
    assert result["first_valid_crossing_step"] == 1
    assert result["official_convergence_implied"] is False


def test_all_invalid_frames_cannot_establish_a_minimum():
    result = threshold_work([frame(1, .01, scf=False)], .02)
    assert result["minimum_valid_fmax_eV_A"] is None


def test_remote_parser_source_compiles_and_has_no_mutation_commands():
    program = reader([{"job_id": "fixture", "atom_count": 50}])
    compile(program, "read_only_snapshot", "exec")
    assert "np.cumsum" not in program
    assert "list(accumulate" in program
    assert "bsub" not in program and "bkill" not in program


def test_transport_rejects_partial_compressed_records():
    with pytest.raises(Exception):
        decode(b"incomplete_base64")
