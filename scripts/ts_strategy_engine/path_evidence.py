from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.artifact_io import load_json_object as _load_json_object, sha256_file, write_json

from .fingerprint import build_fingerprint


def require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise SystemExit(f"{label} not found: {path}")


def load_json_object(path: Path, label: str) -> dict[str, Any]:
    require_file(path, label)
    try:
        payload = _load_json_object(path)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"invalid {label}: {path}") from exc
    return payload


def validate_path_binding(workdir: Path, contract: dict[str, Any]) -> dict[str, Any]:
    report_path = workdir / "path_generation_report.json"
    if not report_path.is_file():
        return {"valid": False, "errors": ["path_generation_report_missing"]}
    report = load_json_object(report_path, "path generation report")
    expected = {
        "contract_sha256": contract["contract_sha256"],
        "atom_map_sha256": contract["atom_map_sha256"],
        "compatibility_sha256": contract["compatibility_sha256"],
        "fingerprint_id": build_fingerprint(contract)["fingerprint_id"],
    }
    errors = [f"{key}_mismatch" for key, value in expected.items() if report.get(key) != value]
    return {
        "valid": not errors,
        "errors": errors,
        "report": str(report_path),
        "report_sha256": sha256_file(report_path),
        **expected,
    }


def validate_path_review(path: Path, path_report: Path) -> tuple[bool, dict[str, Any]]:
    if not path.is_file():
        return False, {}
    payload = load_json_object(path, "path review")
    required = (
        "reviewer",
        "reviewed_at",
        "dist_file",
        "nebmovie_file",
        "dist_sha256",
        "nebmovie_sha256",
        "path_generation_sha256",
    )
    files = _review_files(path, payload)
    accepted = bool(
        payload.get("status") == "accepted"
        and all(payload.get(field) for field in required)
        and path_report.is_file()
        and len(files) == 2
        and all(candidate.is_file() for candidate in files.values())
        and payload.get("path_generation_sha256") == sha256_file(path_report)
        and payload.get("dist_sha256") == sha256_file(files["dist_file"])
        and payload.get("nebmovie_sha256") == sha256_file(files["nebmovie_file"])
    )
    return accepted, payload


def _review_files(review_path: Path, payload: dict[str, Any]) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for field in ("dist_file", "nebmovie_file"):
        value = payload.get(field)
        if value:
            candidate = Path(value)
            files[field] = candidate if candidate.is_absolute() else review_path.parent / candidate
    return files


def write_path_review_draft(
    workdir: Path, dist: Path, nebmovie: Path, output: Path | None = None
) -> Path:
    report = workdir / "path_generation_report.json"
    for path, label in (
        (report, "path generation report"),
        (dist, "dist.pl output"),
        (nebmovie, "nebmovie.pl 0 output"),
    ):
        require_file(path, label)
    destination = output or workdir / "path_review.json"
    if destination.exists():
        raise SystemExit(f"path review already exists: {destination}")
    write_json(
        destination,
        {
            "status": "needs_review",
            "reviewer": None,
            "reviewed_at": None,
            "dist_file": str(dist.resolve()),
            "dist_sha256": sha256_file(dist),
            "nebmovie_file": str(nebmovie.resolve()),
            "nebmovie_sha256": sha256_file(nebmovie),
            "path_generation_sha256": sha256_file(report),
            "notes": None,
        },
    )
    return destination
