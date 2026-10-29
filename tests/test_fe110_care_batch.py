"""Local tests; no model, network, scheduler, or scientific execution."""
from pathlib import Path

import numpy as np
import pytest

from scripts.adsorption.build_fe110_adsorption import Poscar, Site, expanded_symbols
from scripts.adsorption.build_fe110_care_isomers import care_source_pose, equivalent_pose_rmsd, rigid_reanchor_pose
from scripts.adsorption.build_fe110_care_batch import build, molecular_signature
from scripts.adsorption import build_fe110_care_batch as batch


def raw_care():
    return {"ase": {"data": {
        "numbers": [26] * 48 + [6, 8, 6, 1, 1],
        "positions": [[0., 0., 0.]] * 48 + [[4., 4., 8.], [5.4, 4., 8.], [6.7, 4., 8.], [3.5, 4.9, 8.], [3.5, 3.1, 8.]],
        "cell": np.diag([15., 15., 25.]).tolist(),
    }}}


def test_interleaved_ase_atoms_are_reordered_with_a_map_not_relabelled():
    raw = raw_care()
    pose, order = care_source_pose(raw)
    assert order[48:] == [48, 50, 49, 51, 52]
    assert expanded_symbols(pose)[48:] == ["C", "C", "O", "H", "H"]
    assert np.allclose((pose.frac @ pose.cell)[48:], np.array(raw["ase"]["data"]["positions"])[order][48:])


@pytest.mark.parametrize("mutation", ["wrong_Fe_count", "nonfinite", "singular"])
def test_bad_care_inputs_are_rejected(mutation):
    raw = raw_care()
    data = raw["ase"]["data"]
    if mutation == "wrong_Fe_count":
        data["numbers"][0] = 6
    elif mutation == "nonfinite":
        data["positions"][48][0] = float("nan")
    else:
        data["cell"] = np.zeros((3, 3)).tolist()
    with pytest.raises(ValueError):
        care_source_pose(raw)


def c2_pose():
    cell = np.diag([10., 10., 25.])
    ads = np.array([[4., 4., 8.], [5.4, 4., 8.], [3.45, 4.95, 8.], [5.95, 3.05, 8.]])
    return Poscar("test", cell, ["Fe", "C", "H"], [45, 2, 2],
                  np.vstack((np.zeros((45, 3)), ads @ np.linalg.inv(cell))),
                  [("F", "F", "F")] * 18 + [("T", "T", "T")] * 31)


def test_seed_duplicates_include_pbc_h_swap_and_height_only_changes():
    a, b = c2_pose(), c2_pose()
    b.frac[45:, 0] += 1.
    b.frac[45:, 2] += .4 / 25.
    b.frac[[47, 48]] = b.frac[[48, 47]]
    operations = [(np.eye(3), np.zeros(3))]
    assert equivalent_pose_rmsd(a, b, operations) < 1e-12
    assert equivalent_pose_rmsd(a, b, operations, remove_height_shift=False) == pytest.approx(.4)


def test_arbitrary_adsorbate_rotation_is_not_a_surface_symmetry():
    a, b = c2_pose(), c2_pose()
    b.frac[45:, :2] = b.frac[45:, :2][:, ::-1]
    assert equivalent_pose_rmsd(a, b, [(np.eye(3), np.zeros(3))]) > .2


def test_pose_cell_mismatch_is_rejected():
    a, b = c2_pose(), c2_pose()
    b.cell[0, 0] += 1.
    with pytest.raises(ValueError):
        equivalent_pose_rmsd(a, b, [(np.eye(3), np.zeros(3))])


def test_molecular_signature_checks_hydrogen_placement():
    pose = c2_pose()
    assert molecular_signature(pose) == [["C", 1, ["C"]], ["C", 1, ["C"]]]
    pose.frac[48] = np.array([3.45, 3.05, 8.]) @ np.linalg.inv(pose.cell)
    assert molecular_signature(pose) == [["C", 0, ["C"]], ["C", 2, ["C"]]]


def test_detached_hydrogen_is_not_silently_accepted():
    pose = c2_pose()
    pose.frac[48] = [.1, .1, .8]
    with pytest.raises(ValueError, match="hydrogen"):
        molecular_signature(pose)


def test_existing_artifacts_are_never_overwritten(tmp_path):
    marker = tmp_path / "original.txt"
    marker.write_text("preserve", encoding="utf-8")
    with pytest.raises(FileExistsError):
        build(Path("missing-network"), Path("missing-slab"), Path("missing-request"), tmp_path)
    assert marker.read_text(encoding="utf-8") == "preserve"


def test_rigid_reanchor_preserves_internal_bonds_slab_and_flags():
    source = c2_pose()
    slab = Poscar("slab", source.cell.copy(), ["Fe"], [45], source.frac[:45].copy(), source.flags[:45].copy())
    site = Site("top", np.zeros(3), (0,), None)
    result = rigid_reanchor_pose(source, slab, site, anchor=45, axis_to=46,
                                azimuth_deg=45., tilt_deg=20., binding_distance_A=2.15)
    old = source.frac[45:] @ source.cell
    # Unwrap relative to the first adsorbate after the rigid transform.
    relative = result.frac[45:] - result.frac[45]
    relative[:, :2] -= np.round(relative[:, :2])
    new = relative @ result.cell
    assert np.allclose(np.linalg.norm(old[:, None] - old[None, :], axis=2),
                       np.linalg.norm(new[:, None] - new[None, :], axis=2))
    assert np.array_equal(result.frac[:45], slab.frac)
    assert result.flags == source.flags


def test_reanchor_unwraps_long_c_o_c_h_chain_along_bonds():
    cell = np.diag([6., 10., 25.])
    ads = np.array([[.1, 4., 8.], [2.9, 4., 8.], [1.5, 4., 8.], [3.4, 4.95, 8.], [3.8, 3.5, 8.]])
    coords = np.vstack((np.zeros((45, 3)), ads @ np.linalg.inv(cell)))
    source = Poscar("long COC", cell, ["Fe", "C", "O", "H"], [45, 2, 1, 2], coords,
                    [("F", "F", "F")] * 18 + [("T", "T", "T")] * 32)
    slab = Poscar("slab", cell, ["Fe"], [45], coords[:45].copy(), source.flags[:45].copy())
    result = rigid_reanchor_pose(source, slab, Site("top", np.zeros(3), (0,), None),
                                anchor=45, axis_to=47, azimuth_deg=45., tilt_deg=20., binding_distance_A=2.15)
    assert molecular_signature(result) == molecular_signature(source)
    from scripts.adsorption.build_fe110_care_isomers import pair_distances, connectivity
    bonds = connectivity(source, list(range(45, 50)))
    old, new = pair_distances(source, list(range(45, 50))), pair_distances(result, list(range(45, 50)))
    for a, b in bonds:
        assert new[(a + 45, b + 45)] == pytest.approx(old[(a + 45, b + 45)], abs=1e-10)


def test_constructed_seed_prefers_no_warning_without_rejecting_all_warnings(monkeypatch):
    source = c2_pose()
    source.frac[48] = np.array([3.45, 3.05, 8.]) @ np.linalg.inv(source.cell)
    signature = molecular_signature(source)
    calls = []
    monkeypatch.setattr(batch, "rigid_reanchor_pose", lambda *args, **kwargs: source)
    monkeypatch.setattr(batch, "equivalent_pose_rmsd", lambda *args: .8)

    def review_stub(*args):
        calls.append(True)
        return {"verdict": "pass", "warnings": ["soft_height_warning"] if len(calls) == 1 else []}

    monkeypatch.setattr(batch, "review", review_stub)
    _, record = batch.construct_extra(
        source, source, {"top": object()}, [], [(source, {"source_config": "0"})],
        {"id": "test", "anchor_H_count": 0, "signature": signature, "fallback_sites": ["top"]}, .2,
    )
    assert record["attempts"] == 2
    assert record["geometry_review"]["warnings"] == []


def test_success_summary_is_safe_for_a_gbk_terminal(monkeypatch, capsys):
    monkeypatch.setattr(batch, "build", lambda *args: {"candidates": [
        {"name": "06_A", "origin": "local", "geometry_review": {"site_label": "η²(C,C)/lb-lb", "warnings": []}}
    ]})
    monkeypatch.setattr("sys.argv", ["batch", "--network", "n", "--slab", "s", "--request", "r", "--output", "o"])
    batch.main()
    output = capsys.readouterr().out
    assert "eta2(C,C)" in output
    output.encode("gbk")
