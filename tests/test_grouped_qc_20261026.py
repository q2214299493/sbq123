import numpy as np
import pytest

from archive.fe110_grouped_qc_20261026.review import magnetic_status, raw_frames, shortlist
from archive.fe110_10b_lowforce_20261023.review import scf_for_frame


def block(step, moment, force, *, ediff=True):
    return (f"Iteration {step}( 7)\n"
            + ("aborting loop because EDIFF is reached\n" if ediff else "")
            + "magnetization (x)\n# of ion s p d tot\n----\n"
            + f" 1 0.0 0.0 0.0 {moment}\n 2 0.0 0.0 0.0 0.1\n----\n"
            + "POSITION TOTAL-FORCE (eV/Angst)\n----\n"
            + f"0.00000 0.00000 0.00000 {force} 0.0 0.0\n"
            + "1.00000 0.00000 0.00000 0.0 0.0 0.0\n----\n"
            + f"free  energy   TOTEN  = {-10.0-step} eV\n")


def test_force_moments_energy_and_bytes_stay_in_same_ionic_frame(tmp_path):
    path = tmp_path / "OUTCAR"
    data = (block(1, 2.2, .3) + block(2, -1.1, -.4)).encode()
    path.write_bytes(data)
    frames = raw_frames(path, 2)
    assert [f["ionic_step"] for f in frames] == [1, 2]
    assert [f["local_moment_tables"][0][0] for f in frames] == [2.2, -1.1]
    assert [f["forces_eV_per_A"][0][0] for f in frames] == [.3, -.4]
    assert [f["toten_eV"] for f in frames] == [-11, -12]
    for frame in frames:
        start, end = frame["source_byte_range"]
        assert data[start:end] == frame["raw_force_table"]


def test_explicit_ediff_does_not_carry_to_next_frame(tmp_path):
    path = tmp_path / "OUTCAR"
    path.write_text(block(1, 2.2, .3) + block(2, 2.1, .4, ediff=False))
    assert [f["EDIFF_marker_before_force"] for f in raw_frames(path, 2)] == [True, False]


def test_noncontiguous_ionic_identity_rejected(tmp_path):
    path = tmp_path / "OUTCAR"
    path.write_text(block(1, 2.2, .3) + block(3, 2.1, .4))
    with pytest.raises(ValueError, match="missing ionic"):
        raw_frames(path, 2)


def test_incomplete_moment_table_rejected(tmp_path):
    path = tmp_path / "OUTCAR"
    path.write_text(block(1, 2.2, .3).replace(" 2 0.0 0.0 0.0 0.1\n", ""))
    with pytest.raises(ValueError, match="local-moment table"):
        raw_frames(path, 2)


@pytest.mark.parametrize("value", [0, -.1])
def test_any_nonpositive_fe_in_any_table_keeps_magnetic_quarantine(value):
    tables = np.ones((2, 51)) * 2.2
    tables[0, 40] = value
    result = magnetic_status(tables, 51)
    assert result["magnetic_review_level"] == "NEEDS_MAGNETIC_REVIEW"
    assert result["magnetic_global_ground_state_verified"] is False


def test_nelm_boundary_not_admitted_despite_ediff_marker():
    frame = {"ionic_step": 1, "electronic_iteration": 200, "EDIFF_marker_before_force": True}
    cycle = {"ionic_step": 1, "iteration": 200, "complete": True, "malformed": False}
    with pytest.raises(ValueError, match="association"):
        scf_for_frame(frame, cycle, {"NELM": "200", "EDIFF": "1e-5"})


def test_shortlist_keeps_graph_force_strata_and_is_bounded():
    rows = [{"sample_id": str(i), "ionic_step": i, "graph_signature": "A" if i < 10 else "B",
             "movable_fmax_eV_A": .2 if i % 2 else 1.1} for i in range(1, 21)]
    selected = shortlist(rows)
    assert len(selected) == 8
    assert {(r["graph_signature"], r["movable_fmax_eV_A"]) for r in selected} == {("A", .2), ("A", 1.1), ("B", .2), ("B", 1.1)}
    assert shortlist(list(reversed(rows))) == selected
