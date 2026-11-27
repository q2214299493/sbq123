"""Calculate an isothermal reactor profile for an explicitly supplied registered model."""

import argparse
import inspect
import json
from pathlib import Path

from . import simulate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    args = parser.parse_args()

    def unique(rows):
        out = {}
        for key, value in rows:
            if key in out:
                raise ValueError(f"Duplicate JSON key {key}")
            out[key] = value
        return out

    try:
        data = json.loads(args.request.read_bytes(), object_pairs_hook=unique)
        if not isinstance(data, dict):
            raise ValueError("Expected a reactor request object")
        try:
            inspect.signature(simulate).bind(**data)
        except TypeError as exc:
            raise ValueError(str(exc)) from exc
        result = simulate(**data)
    except (OSError, ValueError) as exc:
        parser.exit(
            2,
            json.dumps(
                {
                    "error": str(exc),
                    "failed_local_receipt": getattr(exc, "receipt", None),
                    "prior_local_receipts": getattr(exc, "prior_receipts", []),
                },
                allow_nan=False,
            )
            + "\n",
        )
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
