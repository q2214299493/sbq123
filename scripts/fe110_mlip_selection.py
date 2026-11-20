"""Resolve the hash-bound model for new Fe(110) ML work; never submit jobs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from scripts.artifact_io import require_sha256, sha256_file
from scripts.execution_backends import DEFAULT_CONFIG
from scripts.scientific_validation import finite_number


ROLES = ("adsorption_prerelaxation", "ts_path_search", "active_learning")


def select_model(role: str, *, authority: Path = DEFAULT_CONFIG) -> dict:
    """Bind a new task only; existing explicit model bindings are not resolved here."""
    if role not in ROLES:
        raise ValueError(f"Unknown Fe(110) ML role: {role}")
    config = yaml.safe_load(authority.read_text(encoding="utf-8"))["fe110_mlip_default"]
    if (
        config["family"] != "mace"
        or set(config["roles"]) != set(ROLES)
        or config["calibration"] != "uncalibrated"
        or config["remote_gpu"] != "not_validated"
        or config["training"] != "not_connected"
    ):
        raise ValueError("Unsupported Fe(110) MACE default or unverified capability claim")
    model = config["model"]
    if not {"path", "sha256", "head", "dtype", "required_atomic_numbers"} <= model.keys():
        raise ValueError("Incomplete Fe(110) model binding")
    digest = require_sha256(model["sha256"], label="Fe(110) ML checkpoint")
    if sha256_file(Path(model["path"])) != digest:
        raise ValueError("Selected Fe(110) ML checkpoint hash mismatch; no model fallback")
    selected = {
        "role": role,
        "family": config["family"],
        "model": dict(model),
        "calibration": config["calibration"],
        "remote_gpu": config["remote_gpu"],
        "training": config["training"],
    }
    if role == "adsorption_prerelaxation" and role in config:
        selected["fmax_eV_per_A"] = finite_number(
            config[role]["fmax_eV_per_A"], "MACE adsorption pre-relaxation force threshold", positive=True,
        )
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=ROLES)
    parser.add_argument("--require-remote-ready", action="store_true")
    args = parser.parse_args()
    selected = select_model(args.role)
    if args.require_remote_ready:
        parser.exit(1, "MACE selected; remote runtime not validated. No fallback or submission.\n")
    print(json.dumps(selected, indent=2))


if __name__ == "__main__":
    main()
