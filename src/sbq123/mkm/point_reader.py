"""Read a retained point with installed MKM code in its own interpreter."""

import argparse
import json
import os
from pathlib import Path

from sbq123.common.compat import historical_module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", type=Path)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    os.environ["SBQ123_ROLE_DATA"] = str(args.data.resolve())
    point = historical_module("mkm", "scripts.kinetic_data.comparison_point")
    from sbq123.common.evidence.installation import installed_role

    output = point.export_point(args.run, args.data.resolve())
    output["v32_runtime"] = installed_role("mkm")
    print(json.dumps(output, allow_nan=False))


if __name__ == "__main__":
    main()
