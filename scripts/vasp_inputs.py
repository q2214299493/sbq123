from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from scripts.aqcat25_calibration import parse_poscar_symbols
from scripts.artifact_io import sha256_file
from scripts.vasp_lsf import render_sunboquan_lsf


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "configs" / "true_fe110_production.yaml"
MOMENTS = {"Fe": 2.2, "C": 0.0, "O": 0.0, "H": 0.0}


def _species_counts(symbols: list[str]) -> list[tuple[str, int]]:
    groups: list[tuple[str, int]] = []
    for symbol in symbols:
        if groups and groups[-1][0] == symbol:
            groups[-1] = (symbol, groups[-1][1] + 1)
        else:
            groups.append((symbol, 1))
    return groups


def _format_incar(
    values: dict[str, Any],
    symbols: list[str],
    moments: dict[str, float] | None = None,
) -> str:
    groups = _species_counts(symbols)
    selected_moments = moments or MOMENTS
    if any(symbol not in selected_moments for symbol, _ in groups):
        raise ValueError("MAGMOM rule is undefined for one or more POSCAR species")
    incar = dict(values)
    incar["MAGMOM"] = " ".join(
        f"{count}*{selected_moments[symbol]:.1f}" for symbol, count in groups
    )
    lines = []
    for key, value in incar.items():
        if isinstance(value, bool):
            value = ".TRUE." if value else ".FALSE."
        lines.append(f"{key} = {value}")
    return "\n".join(lines) + "\n"


def build_fe110_adsorption_relaxation(
    destination: Path,
    *,
    cores: int = 32,
    profile_path: Path = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Render one active-branch Fe(110) adsorption relaxation package."""

    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    stage = profile["routine_production"]
    scope = profile["scope"]
    ranks = int(cores)
    if ranks <= 0:
        raise ValueError("VASP MPI ranks must be positive")

    symbols = parse_poscar_symbols(destination / "POSCAR")
    incar = dict(stage["incar"])
    incar.update(
        {
            "GGA": scope["incar_gga"],
            "ENCUT": scope["encut_eV"],
        }
    )
    mesh = stage["gamma_mesh"]
    (destination / "INCAR").write_text(_format_incar(incar, symbols), encoding="ascii")
    (destination / "KPOINTS").write_text(
        f"Gamma mesh\n0\nGamma\n{' '.join(str(value) for value in mesh)}\n0 0 0\n",
        encoding="ascii",
    )
    (destination / "POTCAR.spec").write_text(
        " ".join(dict.fromkeys(symbols)) + "\n", encoding="ascii"
    )
    (destination / "script.lsf").write_text(
        render_sunboquan_lsf(ranks), encoding="ascii", newline="\n"
    )
    return {
        "profile_path": str(profile_path.resolve()),
        "profile_sha256": sha256_file(profile_path),
        "stage": "routine_production",
        "gamma_mesh": mesh,
        "cores": ranks,
        "incar": incar,
    }


def build_fe110_active_learning_force_label(
    destination: Path, *, profile_path: Path = DEFAULT_PROFILE
) -> dict[str, Any]:
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    stage = profile["transition_state"]["active_learning_force_label"]
    base = profile[stage["base_profile"]]
    scope = profile["scope"]
    final_energy_policy = profile["final_energy_policy"]
    compatibility_incar = final_energy_policy.get("required_surface_incar")
    if not isinstance(compatibility_incar, dict) or not {
        "ISMEAR",
        "SIGMA",
    } <= set(compatibility_incar):
        raise ValueError(
            "final_energy_policy.required_surface_incar must define ISMEAR and SIGMA"
        )
    symbols = parse_poscar_symbols(destination / "POSCAR")
    incar = dict(base["incar"])
    incar.update(
        {
            "GGA": scope["incar_gga"],
            "ENCUT": scope["encut_eV"],
            **stage.get("performance_incar", {}),
        }
    )
    # Force labels must target the same electronic branch as the current
    # production data. Apply this last so a legacy static base cannot silently
    # reintroduce an incompatible occupation convention.
    incar.update(compatibility_incar)
    mesh = base["gamma_mesh"]
    (destination / "INCAR").write_text(_format_incar(incar, symbols), encoding="ascii")
    (destination / "KPOINTS").write_text(
        f"Gamma mesh\n0\nGamma\n{' '.join(str(value) for value in mesh)}\n0 0 0\n",
        encoding="ascii",
    )
    (destination / "POTCAR.spec").write_text(" ".join(dict.fromkeys(symbols)) + "\n", encoding="ascii")
    (destination / "script.lsf").write_text(
        render_sunboquan_lsf(int(stage["cores"])), encoding="ascii", newline="\n"
    )
    return {
        "profile_path": str(profile_path.resolve()),
        "profile_sha256": sha256_file(profile_path),
        "stage": "transition_state.active_learning_force_label",
        "base_profile": stage["base_profile"],
        "compatibility_incar_source": "final_energy_policy.required_surface_incar",
        "compatibility_incar": dict(compatibility_incar),
        "final_energy_convention": final_energy_policy["active_convention"],
        "gamma_mesh": mesh,
        "cores": int(stage["cores"]),
        "incar": incar,
    }


def build_fe110_neb(
    destination: Path,
    *,
    images: int,
    stage_name: str = "ordinary_neb",
    cores: int | None = None,
    overrides: dict[str, Any] | None = None,
    magnetic_branch: str | None = None,
    profile_path: Path = DEFAULT_PROFILE,
) -> dict[str, Any]:
    if images < 1:
        raise ValueError("NEB requires at least one interior image")
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    stage = (
        profile[stage_name]
        if stage_name == "ordinary_neb"
        else profile["transition_state"].get(stage_name)
    )
    if stage is None or stage_name not in {"ordinary_neb", "refine_neb", "ci_neb"}:
        raise ValueError(f"unsupported NEB stage: {stage_name}")
    policy = profile["transition_state"]["parameter_policy"]
    allowed = {str(key).upper() for key in policy["allowed_to_vary_by_approved_stage"][stage_name]}
    requested = {str(key).upper(): value for key, value in (overrides or {}).items()}
    forbidden = sorted(set(requested) - allowed)
    if forbidden:
        raise ValueError("stage override is not allowed: " + ", ".join(forbidden))
    moments = MOMENTS
    if magnetic_branch:
        branch = policy.get("approved_magnetic_initialization_branches", {}).get(
            magnetic_branch
        )
        if branch is None or stage_name not in branch.get("stages", []):
            raise ValueError("magnetic initialization branch is not approved for this stage")
        moments = {str(symbol): float(value) for symbol, value in branch["moments_muB"].items()}
    symbols = parse_poscar_symbols(destination / "00" / "POSCAR")
    incar = dict(stage["incar"])
    incar.update(stage.get("performance_incar", {}))
    incar.update(
        {
            "GGA": profile["scope"]["incar_gga"],
            "ENCUT": profile["scope"]["encut_eV"],
            "IMAGES": images,
        }
    )
    incar.update(requested)
    mesh = stage["gamma_mesh"]
    ranks = int(cores or stage.get("cores", 0))
    if ranks <= 0 or ranks % images:
        raise ValueError("VASP MPI ranks must be positive and divisible by IMAGES")
    (destination / "INCAR").write_text(
        _format_incar(incar, symbols, moments), encoding="ascii"
    )
    (destination / "KPOINTS").write_text(
        f"Gamma mesh\n0\nGamma\n{' '.join(str(value) for value in mesh)}\n0 0 0\n",
        encoding="ascii",
    )
    (destination / "POTCAR.spec").write_text(" ".join(dict.fromkeys(symbols)) + "\n", encoding="ascii")
    (destination / "script.lsf").write_text(
        render_sunboquan_lsf(ranks), encoding="ascii", newline="\n"
    )
    return {
        "profile_path": str(profile_path.resolve()),
        "profile_sha256": sha256_file(profile_path),
        "stage": stage_name,
        "gamma_mesh": mesh,
        "cores": ranks,
        "images": images,
        "magnetic_branch": magnetic_branch or "default",
        "incar": incar,
    }


def build_fe110_dimer(
    destination: Path,
    *,
    cores: int,
    overrides: dict[str, Any] | None = None,
    profile_path: Path = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Render the reviewed Fe(110) DIMER stage from the project profile."""

    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    stage = profile["transition_state"]["dimer"]
    policy = profile["transition_state"]["parameter_policy"]
    allowed = {
        str(key).upper()
        for key in policy["allowed_to_vary_by_approved_stage"]["dimer"]
    }
    requested = {str(key).upper(): value for key, value in (overrides or {}).items()}
    forbidden = sorted(set(requested) - allowed)
    if forbidden:
        raise ValueError("stage override is not allowed: " + ", ".join(forbidden))

    symbols = parse_poscar_symbols(destination / "POSCAR")
    incar = dict(stage["incar"])
    incar.update(
        {
            "GGA": profile["scope"]["incar_gga"],
            "ENCUT": profile["scope"]["encut_eV"],
        }
    )
    incar.update(requested)
    mesh = policy["fixed_dft_basis"]["gamma_mesh"]
    ranks = int(cores)
    if ranks <= 0:
        raise ValueError("VASP MPI ranks must be positive")

    (destination / "INCAR").write_text(
        _format_incar(incar, symbols), encoding="ascii"
    )
    (destination / "KPOINTS").write_text(
        f"Gamma mesh\n0\nGamma\n{' '.join(str(value) for value in mesh)}\n0 0 0\n",
        encoding="ascii",
    )
    (destination / "POTCAR.spec").write_text(
        " ".join(dict.fromkeys(symbols)) + "\n", encoding="ascii"
    )
    (destination / "script.lsf").write_text(
        render_sunboquan_lsf(ranks), encoding="ascii", newline="\n"
    )
    return {
        "profile_path": str(profile_path.resolve()),
        "profile_sha256": sha256_file(profile_path),
        "stage": "dimer",
        "gamma_mesh": mesh,
        "cores": ranks,
        "magnetic_branch": "default_fe_2p2_muB",
        "incar": incar,
    }


def build_fe110_vfa(
    destination: Path,
    *,
    cores: int,
    overrides: dict[str, Any] | None = None,
    profile_path: Path = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Render the reviewed partial-Hessian frequency stage."""

    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    stage = profile["transition_state"]["vfa"]
    policy = profile["transition_state"]["parameter_policy"]
    allowed = {
        str(key).upper()
        for key in policy["allowed_to_vary_by_approved_stage"]["vfa"]
        if key not in {"active_atom_set", "core_count"}
    }
    requested = {str(key).upper(): value for key, value in (overrides or {}).items()}
    forbidden = sorted(set(requested) - allowed)
    if forbidden:
        raise ValueError("stage override is not allowed: " + ", ".join(forbidden))
    ranks = int(cores)
    if ranks <= 0:
        raise ValueError("VASP MPI ranks must be positive")

    symbols = parse_poscar_symbols(destination / "POSCAR")
    incar = dict(stage["incar"])
    incar.update(
        {
            "GGA": profile["scope"]["incar_gga"],
            "ENCUT": profile["scope"]["encut_eV"],
        }
    )
    incar.update(requested)
    mesh = policy["fixed_dft_basis"]["gamma_mesh"]
    (destination / "INCAR").write_text(_format_incar(incar, symbols), encoding="ascii")
    (destination / "KPOINTS").write_text(
        f"Gamma mesh\n0\nGamma\n{' '.join(str(value) for value in mesh)}\n0 0 0\n",
        encoding="ascii",
    )
    (destination / "POTCAR.spec").write_text(
        " ".join(dict.fromkeys(symbols)) + "\n", encoding="ascii"
    )
    (destination / "script.lsf").write_text(
        render_sunboquan_lsf(ranks), encoding="ascii", newline="\n"
    )
    return {
        "profile_path": str(profile_path.resolve()),
        "profile_sha256": sha256_file(profile_path),
        "stage": "vfa",
        "gamma_mesh": mesh,
        "cores": ranks,
        "incar": incar,
    }


def build_fe110_connectivity_relax(
    destination: Path,
    *,
    cores: int | None = None,
    overrides: dict[str, Any] | None = None,
    profile_path: Path = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Render one contract-bound downhill TS-connectivity relaxation."""

    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    stage = profile["transition_state"]["connectivity_relax"]
    policy = profile["transition_state"]["parameter_policy"]
    allowed = {
        str(key).upper()
        for key in policy["allowed_to_vary_by_approved_stage"]["connectivity_relax"]
        if key != "core_count"
    }
    requested = {str(key).upper(): value for key, value in (overrides or {}).items()}
    forbidden = sorted(set(requested) - allowed)
    if forbidden:
        raise ValueError("stage override is not allowed: " + ", ".join(forbidden))
    ranks = int(cores or stage["cores"])
    if ranks <= 0:
        raise ValueError("VASP MPI ranks must be positive")
    symbols = parse_poscar_symbols(destination / "POSCAR")
    incar = dict(stage["incar"])
    incar.update(
        {
            "GGA": profile["scope"]["incar_gga"],
            "ENCUT": profile["scope"]["encut_eV"],
        }
    )
    incar.update(requested)
    mesh = policy["fixed_dft_basis"]["gamma_mesh"]
    (destination / "INCAR").write_text(_format_incar(incar, symbols), encoding="ascii")
    (destination / "KPOINTS").write_text(
        f"Gamma mesh\n0\nGamma\n{' '.join(str(value) for value in mesh)}\n0 0 0\n",
        encoding="ascii",
    )
    (destination / "POTCAR.spec").write_text(
        " ".join(dict.fromkeys(symbols)) + "\n", encoding="ascii"
    )
    (destination / "script.lsf").write_text(
        render_sunboquan_lsf(ranks), encoding="ascii", newline="\n"
    )
    return {
        "profile_path": str(profile_path.resolve()),
        "profile_sha256": sha256_file(profile_path),
        "stage": "connectivity_relax",
        "gamma_mesh": mesh,
        "cores": ranks,
        "incar": incar,
    }
