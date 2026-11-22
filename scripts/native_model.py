"""Assemble immutable local input bundles. This module has no execution entry point."""
import argparse
import json
import tempfile
from pathlib import Path

from scripts.artifact_io import sha256_bytes, sha256_json
from scripts.kinetic_parameters.export import catkinas, zacros
from scripts.multiphase_contracts import read_unique_json as read
from scripts.native_inputs import conditions as conditions, integer as integer, token as token


def assemble(engine, dataset, config, table=None):
    from scripts.baseline_mkm.mapping_scope import check_table_scope
    from scripts.baseline_mkm.native import render as render_cat
    from scripts.surface_kmc.native import render as render_zac
    from scripts.native_validation import cat_readback, zac_readback
    exporter, render = {"catkinas": (catkinas, render_cat), "zacros": (zacros, render_zac)}[engine]
    expected = exporter(dataset)
    if table is not None and sha256_json(table) != sha256_json(expected):
        raise ValueError("Supplied table differs from approved Phase 2.4 export")
    if engine == "catkinas":
        check_table_scope(dataset, expected)
    files, details = render(expected, config, dataset)
    if engine == "catkinas":
        details["native_text_readback"] = cat_readback(files, expected, details, initial_coverages=config["catkinas"]["initial_coverages"])
    else:
        details["native_text_readback"] = zac_readback(files, expected, details)
    manifest = {"engine": engine, "dataset_version": dataset["dataset_version"], "table_sha256": sha256_json(expected),
                "configuration_sha256": sha256_json(config), "files": {k: sha256_bytes(v.encode()) for k, v in files.items()},
                "validation": details, "execution_authorized": False}
    return files, manifest


def publish(directory, files, manifest):
    directory = Path(directory)
    contents = dict(files, **{"manifest.json": json.dumps(manifest, indent=2, allow_nan=False) + "\n"})
    contents = {k: v.encode() if isinstance(v, str) else v for k, v in contents.items()}
    directory.parent.mkdir(parents=True, exist_ok=True)
    if directory.exists():
        if ({p.name for p in directory.iterdir()} != set(contents)
                or any((directory / k).read_bytes() != v for k, v in contents.items())):
            raise ValueError("Existing model directory differs or contains run outputs")
        return
    with tempfile.TemporaryDirectory(dir=directory.parent) as staging:
        bundle = Path(staging) / "model"
        bundle.mkdir()
        for k, v in contents.items():
            (bundle / k).write_bytes(v)
        bundle.rename(directory)


def with_checkpoint(files, manifest, raw, receipt):
    """Stage an existing checkpoint whose receipt binds its producing model and exact bytes."""
    if manifest["engine"] != "zacros" or "no_restart" in files["simulation_input.dat"].splitlines():
        raise ValueError("Resume requires a Zacros checkpoint-enabled model")
    if (not raw or receipt.get("model_sha256") != sha256_json(manifest)
            or receipt.get("checkpoint_sha256") != sha256_bytes(raw)):
        raise ValueError("Checkpoint receipt differs from requested model or bytes")
    actual = {name: sha256_bytes(content.encode() if isinstance(content, str) else content) for name, content in files.items()}
    if manifest["files"] != actual:
        raise ValueError("Input files differ from the checkpoint-producing model")
    return dict(files, **{"restart.inf": raw}), dict(manifest, restart_receipt=receipt,
            files={**manifest["files"], "restart.inf": sha256_bytes(raw)})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("engine", choices=["catkinas", "zacros"])
    for arg in ("dataset", "configuration", "directory"):
        p.add_argument(arg, type=Path)
    p.add_argument("--table", type=Path)
    p.add_argument("--checkpoint", type=Path)
    p.add_argument("--checkpoint-receipt", type=Path)
    args = p.parse_args()
    files, manifest = assemble(args.engine, read(args.dataset), read(args.configuration), read(args.table) if args.table else None)
    if bool(args.checkpoint) != bool(args.checkpoint_receipt):
        p.error("Supply both checkpoint and its model-bound receipt")
    if args.checkpoint:
        files, manifest = with_checkpoint(files, manifest, args.checkpoint.read_bytes(), read(args.checkpoint_receipt))
    publish(args.directory, files, manifest)


if __name__ == "__main__":
    main()
