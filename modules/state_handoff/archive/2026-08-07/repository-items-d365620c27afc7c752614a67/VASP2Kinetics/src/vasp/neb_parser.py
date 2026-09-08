"""Parse existing numeric VASP NEB image directories."""

from __future__ import annotations

import logging
from pathlib import Path

from .outcar_parser import parse_outcar

LOGGER = logging.getLogger("vasp2kinetics.vasp.neb")


def find_neb_image_directories(path: str | Path) -> list[Path]:
    """Return numeric child directories sorted by their integer image ID."""

    neb_path = Path(path)
    if not neb_path.is_dir():
        return []
    return sorted(
        (
            child
            for child in neb_path.iterdir()
            if child.is_dir() and child.name.isdecimal()
        ),
        key=lambda child: int(child.name),
    )


def parse_neb(path: str | Path) -> dict[str, object]:
    """Read each image OUTCAR and identify the highest recorded image energy."""

    neb_path = Path(path)
    if not neb_path.is_dir():
        LOGGER.error("NEB directory does not exist: %s", neb_path)
        return {
            "status": "NOT_AVAILABLE",
            "images": [],
            "highest_image": None,
            "highest_energy": None,
            "error": "NEB_DIRECTORY_NOT_FOUND",
        }

    try:
        image_directories = find_neb_image_directories(neb_path)
    except OSError:
        LOGGER.exception("Unable to inspect NEB directory: %s", neb_path)
        return {
            "status": "ERROR",
            "images": [],
            "highest_image": None,
            "highest_energy": None,
            "error": "NEB_DIRECTORY_READ_ERROR",
        }

    if not image_directories:
        LOGGER.error("No numeric image directories found: %s", neb_path)
        return {
            "status": "NOT_AVAILABLE",
            "images": [],
            "highest_image": None,
            "highest_energy": None,
            "error": "NEB_IMAGES_NOT_FOUND",
        }

    images: list[dict[str, object]] = []
    available_energies: list[tuple[int, float]] = []
    incomplete = False

    for image_directory in image_directories:
        image_id = int(image_directory.name)
        outcar_result = parse_outcar(image_directory / "OUTCAR")
        energy = outcar_result["energy_final"]
        image: dict[str, object] = {"id": image_id, "energy": energy}

        error = outcar_result.get("error")
        if isinstance(error, str):
            image["error"] = error
            incomplete = True

        if isinstance(energy, float):
            available_energies.append((image_id, energy))
        else:
            incomplete = True

        images.append(image)

    if available_energies:
        highest_image, highest_energy = max(
            available_energies,
            key=lambda item: item[1],
        )
    else:
        highest_image = None
        highest_energy = None

    result: dict[str, object] = {
        "status": "INCOMPLETE" if incomplete else "AVAILABLE",
        "images": images,
        "highest_image": highest_image,
        "highest_energy": highest_energy,
    }
    if incomplete:
        result["error"] = "NEB_IMAGE_DATA_INCOMPLETE"
        LOGGER.warning("NEB image data are incomplete: %s", neb_path)

    return result
