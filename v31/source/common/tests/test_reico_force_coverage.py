from __future__ import annotations

import numpy as np
import pytest

from scripts.adsorption.reico_force_coverage import force_coverage, force_histogram, matched_force_difference, nearby_force_pairs
from tests.test_reico_environment_audit import slab


def test_equal_element_permutations_and_pbc_keep_force_correspondence():
    first = slab()
    order = list(range(45))+[46,45,47,48]
    second = first[order]
    second.positions[45:,0] += first.cell[0,0]
    forces = np.arange(len(first)*3,dtype=float).reshape(-1,3)/10
    result = matched_force_difference(first,second,forces,forces[order])
    assert result["geometry_RMSD_A"] < 1e-12
    assert result["adsorbate"]["maximum_vector_difference_eV_A"] == 0
    assert result["second_atom_for_each_first_0based"][45:47] == [46,45]


def test_raw_fixed_forces_are_preserved_but_excluded_from_movable_metrics():
    atoms = slab()
    one,two = np.zeros((len(atoms),3)),np.zeros((len(atoms),3))
    two[0] = [1000,0,0]
    two[45:] = [3,4,0]
    result = matched_force_difference(atoms,atoms,one,two)
    assert result["adsorbate"]["vector_RMSE_difference_eV_A"] == 5
    assert result["movable_Fe"]["maximum_vector_difference_eV_A"] == 0
    assert two[0,0] == 1000


@pytest.mark.parametrize("bad", [np.zeros((2,3)),np.full((49,3),np.nan)])
def test_bad_force_arrays_are_rejected(bad):
    atoms = slab()
    with pytest.raises(ValueError,match="force array"):
        matched_force_difference(atoms,atoms,bad,np.zeros((len(atoms),3)))


def test_histogram_includes_large_forces_without_filtering():
    result = force_histogram([.01,.05,.2,20],[0,.05,.1,1,10])
    assert sum(result.values()) == 4 and result["[10,inf)"] == 1
    assert result["[0.05,0.1)"] == 1


@pytest.mark.parametrize("values", [[np.nan],[-1]])
def test_invalid_force_norms_cannot_enter_bins(values):
    with pytest.raises(ValueError):
        force_histogram(values,[0,1])


def test_coverage_and_pairs_reject_reserved_labels_before_reading_forces():
    row = {"sample_id":"reserved","partition":"final_test","forces_eV_per_A":"DO_NOT_USE"}
    with pytest.raises(ValueError,match="training labels only"):
        force_coverage([row],{},[0,.05,1])
    with pytest.raises(ValueError,match="training labels only"):
        nearby_force_pairs([row],{}, {},.2)


def test_large_nearby_force_difference_is_diagnostic_and_not_deleted():
    one,two = slab(),slab()
    two.positions[45:,0] += .1
    rows = []
    for name,force,mag in (("one",0.,105.),("two",5.,106.)):
        rows.append({"sample_id":name,"family_id":"same","composition":"C2HO","partition":"train",
                     "forces_eV_per_A":np.full((len(one),3),force).tolist(),
                     "total_magnetization_muB":mag,"local_magnetization_muB":[2.2]*45+[0.]*4})
    geometry={"one":{"graph_signature":"a","joint_signature":"a"},"two":{"graph_signature":"b","joint_signature":"b"}}
    pairs=nearby_force_pairs(rows,{"one":one,"two":two},geometry,.2)
    assert len(pairs)==1 and not pairs[0]["same_graph"]
    assert pairs[0]["adsorbate"]["vector_RMSE_difference_eV_A"] > 8
    assert pairs[0]["total_moment_difference_muB"] == 1
    assert len(rows)==2


def test_numbered_electronic_cycle_keeps_ediff_after_sigma_energy(tmp_path):
    from scripts.vasp_result_gate import final_scf_status

    (tmp_path/"INCAR").write_text("NELM = 200\nEDIFF = 1e-5\n",encoding="ascii")
    (tmp_path/"OSZICAR").write_text("DAV: 56 -0.371865942528E+03 -0.22875E-04 -0.26508E-04\n",encoding="ascii")
    (tmp_path/"OUTCAR").write_text(
        "Iteration 1( 56)\nenergy(sigma->0) = -100.125\n"
        "aborting loop because EDIFF is reached\n"
        "General timing and accounting informations for this job:\n",encoding="ascii",
    )
    status=final_scf_status(tmp_path/"OSZICAR",tmp_path/"INCAR",tmp_path/"OUTCAR")
    assert status["electronically_converged"]
    assert status["electronic_convergence_source"] == "OUTCAR_EDIFF_TERMINATION"
