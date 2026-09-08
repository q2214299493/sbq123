"""Load a user-authored surface definition and write lattice metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..exceptions import ZacrosGenerationError


@dataclass(frozen=True)
class SurfaceConfig:
    """Explicit surface labels and reaction-to-site assignments."""

    material: str
    facet: str | int
    sites: tuple[str, ...]
    reaction_sites: dict[str, str]


def _required_text(data: dict[str, Any], key: str, section: str) -> str:
    """Return one required non-empty surface string."""

    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ZacrosGenerationError(
            f"Surface field '{section}.{key}' must be a non-empty string."
        )
    return value.strip()


def _required_facet(data: dict[str, Any]) -> str | int:
    """Return the explicit YAML facet scalar without scientific interpretation."""

    value = data.get("facet")
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ZacrosGenerationError(
            "Surface field 'surface.facet' must be a non-empty string or integer."
        )
    if isinstance(value, str) and not value.strip():
        raise ZacrosGenerationError(
            "Surface field 'surface.facet' must be a non-empty string or integer."
        )
    return value.strip() if isinstance(value, str) else value


def load_surface_config(path: str | Path) -> SurfaceConfig:
    """Read strict user-provided lattice labels without interpreting them."""

    config_path = Path(path).expanduser().resolve()
    if not config_path.is_file():
        raise ZacrosGenerationError(f"Surface configuration does not exist: {config_path}")
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ZacrosGenerationError(
            f"Invalid YAML in surface configuration: {config_path}"
        ) from exc
    except OSError as exc:
        raise ZacrosGenerationError(
            f"Unable to read surface configuration: {config_path}"
        ) from exc
    if not isinstance(raw, dict):
        raise ZacrosGenerationError("Surface configuration root must be a mapping.")
    if set(raw) - {"surface", "reaction_sites"}:
        raise ZacrosGenerationError("Surface configuration contains unsupported fields.")

    surface = raw.get("surface")
    if not isinstance(surface, dict):
        raise ZacrosGenerationError("Surface configuration requires a 'surface' mapping.")
    if set(surface) - {"material", "facet", "sites"}:
        raise ZacrosGenerationError("Surface mapping contains unsupported fields.")

    sites = surface.get("sites")
    if (
        not isinstance(sites, list)
        or not sites
        or any(not isinstance(site, str) or not site.strip() for site in sites)
    ):
        raise ZacrosGenerationError("Surface sites must be a non-empty string list.")
    normalized_sites = tuple(site.strip() for site in sites)
    if len(set(normalized_sites)) != len(normalized_sites):
        raise ZacrosGenerationError("Surface sites must not contain duplicates.")

    reaction_sites_raw = raw.get("reaction_sites", {})
    if not isinstance(reaction_sites_raw, dict):
        raise ZacrosGenerationError("reaction_sites must be a mapping.")
    reaction_sites: dict[str, str] = {}
    for reaction_id, site in reaction_sites_raw.items():
        if (
            not isinstance(reaction_id, str)
            or not reaction_id.strip()
            or not isinstance(site, str)
            or not site.strip()
        ):
            raise ZacrosGenerationError(
                "reaction_sites keys and values must be non-empty strings."
            )
        reaction_sites[reaction_id.strip()] = site.strip()

    return SurfaceConfig(
        material=_required_text(surface, "material", "surface"),
        facet=_required_facet(surface),
        sites=normalized_sites,
        reaction_sites=reaction_sites,
    )


def write_lattice_file(config: SurfaceConfig, path: str | Path) -> Path:
    """Write only the user-provided material, facet, and site labels."""

    lines = [f"material: {config.material}", f"facet: {config.facet}"]
    lines.extend(f"site_type: {site}" for site in config.sites)
    output_path = Path(path)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path
