from __future__ import annotations

from pathlib import Path

import pytest

from scripts.vasp_inputs import (
    build_fe110_adsorption_relaxation,
    build_fe110_active_learning_force_label,
    build_fe110_dimer,
    build_fe110_neb,
    build_fe110_vfa,
)


POSCAR = """Fe45 C O
1.0
10 0 0
0 10 0
0 0 20
Fe C O
45 1 1
Selective dynamics
Direct
""" + "\n".join(["0 0 0 F F F"] * 45 + ["0.2 0.2 0.6 T T T", "0.3 0.3 0.6 T T T"]) + "\n"

ADSORPTION_POSCAR = """Fe45 C H
1.0
10 0 0
0 10 0
0 0 20
Fe C H
45 1 1
Selective dynamics
Direct
""" + "\n".join(
    ["0 0 0 F F F"] * 18
    + ["0 0 0 T T T"] * 27
    + ["0.2 0.2 0.6 T T T", "0.3 0.3 0.6 T T T"]
) + "\n"


def test_adsorption_builder_uses_active_profile_and_dynamic_species_counts(
    tmp_path: Path,
) -> None:
    (tmp_path / "POSCAR").write_text(ADSORPTION_POSCAR, encoding="ascii")
    report = build_fe110_adsorption_relaxation(tmp_path)
    incar = (tmp_path / "INCAR").read_text(encoding="ascii")
    assert report["stage"] == "routine_production"
    assert report["cores"] == 32
    assert "EDIFFG = -0.02" in incar
    assert "NSW = 300" in incar
    assert "MAGMOM = 45*2.2 1*0.0 1*0.0" in incar
    assert "5 5 1" in (tmp_path / "KPOINTS").read_text(encoding="ascii")
    assert "NP=32" in (tmp_path / "script.lsf").read_text(encoding="ascii")


def test_active_learning_force_label_uses_current_final_energy_branch(
    tmp_path: Path,
) -> None:
    (tmp_path / "POSCAR").write_text(ADSORPTION_POSCAR, encoding="ascii")
    report = build_fe110_active_learning_force_label(tmp_path)
    incar = (tmp_path / "INCAR").read_text(encoding="ascii")
    assert report["compatibility_incar_source"] == (
        "final_energy_policy.required_surface_incar"
    )
    assert report["final_energy_convention"] == "fe110_converged_toten_sigma0p20_v1"
    assert report["compatibility_incar"] == {"ISMEAR": 1, "SIGMA": 0.20}
    assert "ISMEAR = 1\nSIGMA = 0.2\n" in incar
    assert "NSW = 0" in incar
    assert "LORBIT = 11" in incar


def test_neb_builder_uses_one_profile_and_divisible_ranks(tmp_path: Path) -> None:
    image = tmp_path / "00"
    image.mkdir()
    (image / "POSCAR").write_text(POSCAR, encoding="ascii")
    report = build_fe110_neb(tmp_path, images=8, cores=128, overrides={"ALGO": "Normal"})
    incar = (tmp_path / "INCAR").read_text(encoding="ascii")
    assert report["stage"] == "ordinary_neb"
    assert "IMAGES = 8" in incar
    assert "ALGO = Normal" in incar
    assert "LCLIMB = .FALSE." in incar
    assert "NP=128" in (tmp_path / "script.lsf").read_text(encoding="ascii")


def test_neb_builder_rejects_locked_basis_override(tmp_path: Path) -> None:
    image = tmp_path / "00"
    image.mkdir()
    (image / "POSCAR").write_text(POSCAR, encoding="ascii")
    with pytest.raises(ValueError, match="not allowed"):
        build_fe110_neb(tmp_path, images=8, cores=128, overrides={"ENCUT": 500})


def test_neb_builder_uses_only_an_approved_magnetic_branch(tmp_path: Path) -> None:
    image = tmp_path / "00"
    image.mkdir()
    (image / "POSCAR").write_text(POSCAR, encoding="ascii")
    report = build_fe110_neb(
        tmp_path,
        images=8,
        cores=128,
        magnetic_branch="fe110_co_dissociation_highspin_seed_v1",
    )
    assert report["magnetic_branch"] == "fe110_co_dissociation_highspin_seed_v1"
    assert "MAGMOM = 45*2.4 1*0.0 1*0.0" in (tmp_path / "INCAR").read_text(
        encoding="ascii"
    )

    with pytest.raises(ValueError, match="not approved"):
        build_fe110_neb(
            tmp_path,
            images=8,
            cores=128,
            magnetic_branch="unreviewed_branch",
        )


def test_dimer_builder_uses_reviewed_profile_and_default_fe_moments(
    tmp_path: Path,
) -> None:
    (tmp_path / "POSCAR").write_text(POSCAR, encoding="ascii")
    report = build_fe110_dimer(tmp_path, cores=32)
    incar = (tmp_path / "INCAR").read_text(encoding="ascii")
    assert report["stage"] == "dimer"
    assert report["cores"] == 32
    assert "ICHAIN = 2" in incar
    assert "IOPT = 2" in incar
    assert "DdR = 0.005" in incar
    assert "EDIFF = 1e-07" in incar
    assert "MAGMOM = 45*2.2 1*0.0 1*0.0" in incar
    assert "5 5 1" in (tmp_path / "KPOINTS").read_text(encoding="ascii")
    assert "NP=32" in (tmp_path / "script.lsf").read_text(encoding="ascii")


def test_dimer_builder_rejects_locked_basis_override(tmp_path: Path) -> None:
    (tmp_path / "POSCAR").write_text(POSCAR, encoding="ascii")
    with pytest.raises(ValueError, match="not allowed"):
        build_fe110_dimer(tmp_path, cores=32, overrides={"ENCUT": 500})


def test_vfa_builder_uses_finite_difference_profile(tmp_path: Path) -> None:
    (tmp_path / "POSCAR").write_text(POSCAR, encoding="ascii")
    report = build_fe110_vfa(tmp_path, cores=32)
    incar = (tmp_path / "INCAR").read_text(encoding="ascii")
    assert report["stage"] == "vfa"
    assert "IBRION = 5" in incar
    assert "NFREE = 2" in incar
    assert "POTIM = 0.015" in incar
    assert "NSW = 1" in incar
    assert "NP=32" in (tmp_path / "script.lsf").read_text(encoding="ascii")


def test_vfa_builder_rejects_locked_basis_override(tmp_path: Path) -> None:
    (tmp_path / "POSCAR").write_text(POSCAR, encoding="ascii")
    with pytest.raises(ValueError, match="not allowed"):
        build_fe110_vfa(tmp_path, cores=32, overrides={"ENCUT": 500})
