from __future__ import annotations

from scripts.adsorption.build_gas_cho_chxo import build as build_cho_chxo
from scripts.adsorption.build_gas_h2_chx import build as build_h2_chx
from scripts.adsorption.build_gas_oxygenated_isomers import build as build_oxygenated_isomers
from scripts.adsorption.build_gas_step12a_references import build as build_step12a_references
from scripts.adsorption.preflight_gas_references import audit as audit_step12a_references


def test_all_gas_builders_share_complete_vasp_contract(tmp_path) -> None:
    builders = (build_h2_chx, build_cho_chxo, build_oxygenated_isomers, build_step12a_references)
    for index, builder in enumerate(builders):
        builder(tmp_path / str(index))

    relax_dirs = sorted(tmp_path.rglob("relax"))
    assert len(relax_dirs) == 17
    required = {"POSCAR", "INCAR", "KPOINTS", "job.sh", "POTCAR.spec"}
    for folder in relax_dirs:
        assert required <= {path.name for path in folder.iterdir()}
        incar = (folder / "INCAR").read_text(encoding="ascii")
        assert "GGA = PE" in incar
        assert "ENCUT = 400" in incar
        assert "ISPIN = 1" in incar or "ISPIN = 2" in incar
        assert (folder / "KPOINTS").read_text(encoding="ascii").endswith("1 1 1\n0 0 0\n")


def test_closed_shell_and_radical_spin_contracts(tmp_path) -> None:
    build_cho_chxo(tmp_path)

    closed_shell = (tmp_path / "CH2O" / "relax" / "INCAR").read_text(encoding="ascii")
    radical = (tmp_path / "CHO" / "relax" / "INCAR").read_text(encoding="ascii")
    assert "ISPIN = 1" in closed_shell and "MAGMOM" not in closed_shell
    assert "ISPIN = 2" in radical and "MAGMOM" in radical and "NUPDOWN" in radical


def test_step12a_reference_spin_and_potcar_contracts(tmp_path) -> None:
    build_step12a_references(tmp_path)

    expected = {
        "CO": ("ISPIN = 1", None, "C_O"),
        "H": ("NUPDOWN = 1", "MAGMOM = 1*1.0", "H"),
        "O": ("NUPDOWN = 2", "MAGMOM = 1*2.0", "O"),
        "OH": ("NUPDOWN = 1", "MAGMOM = 1*1.0 1*0.0", "O_H"),
        "C": ("NUPDOWN = 2", "MAGMOM = 1*2.0", "C"),
    }
    for species, (spin, magmom, potcar) in expected.items():
        folder = tmp_path / species / "relax"
        incar = (folder / "INCAR").read_text(encoding="ascii")
        assert spin in incar
        if magmom is None:
            assert "MAGMOM" not in incar
        else:
            assert magmom in incar
        assert (folder / "POTCAR.spec").read_text(encoding="ascii").strip() == potcar


def test_step12a_reference_preflight_detects_method_drift(tmp_path) -> None:
    build_step12a_references(tmp_path)
    assert audit_step12a_references(tmp_path)["passed"] is True

    incar = tmp_path / "O" / "relax" / "INCAR"
    incar.write_text(
        incar.read_text(encoding="ascii").replace("NUPDOWN = 2", "NUPDOWN = 0"),
        encoding="ascii",
    )
    result = audit_step12a_references(tmp_path)
    assert result["passed"] is False
    assert result["records"][2]["failures"] == ["INCAR NUPDOWN='0', expected '2'"]
