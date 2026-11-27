"""Generate a parameter dataset, missing-parameter report, or engine-specific parameter table."""
import argparse
import json
from pathlib import Path

from scripts.artifact_io import sha256_file, sha256_json, write_json_exclusive
from scripts.kinetic_parameters.engine import generate
from scripts.kinetic_parameters.export import catkinas, zacros
from scripts.multiphase_contracts import read_unique_json as read


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("network", type=Path)
    parser.add_argument("--models", type=Path)
    parser.add_argument("--evidence", type=Path, action="append", default=[])
    parser.add_argument("--format", choices=["dataset", "missing", "catkinas", "zacros"], default="dataset")
    parser.add_argument("--output", type=Path, help="Write once, or verify identical existing contents")
    args = parser.parse_args()
    data = generate(read(args.network), read(args.models) if args.models else None,
                    verified_hashes=[sha256_file(p) for p in args.evidence])
    result = data
    if args.format == "missing":
        result = {"network_version": data["network_version"], "dataset_version": data["dataset_version"],
                  "export_eligible": data["export_eligible"], "reactions": [
                      {k: r[k] for k in ("reaction_id", "network_level", "energies", "ts_local_zpe_ev", "rates", "missing", "local_event_missing")}
                      for r in data["reactions"]]}
    if args.format in ("catkinas", "zacros"):
        result = {"catkinas": catkinas, "zacros": zacros}[args.format](data)
    if args.output:
        try:
            write_json_exclusive(args.output, result)
        except FileExistsError:
            if sha256_json(read(args.output)) != sha256_json(result):
                raise ValueError("Existing output differs; choose a new file") from None
    else:
        print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
