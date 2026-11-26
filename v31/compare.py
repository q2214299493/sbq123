"""Compare a hash-bound request using the two source roles materialized from this release."""
import argparse
import json
from pathlib import Path
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("pair", type=Path)
parser.add_argument("request", type=Path)
parser.add_argument("sha256")
args = parser.parse_args()
if not sys.flags.isolated or not sys.dont_write_bytecode:
    parser.error("Run with python -I -B")
pair = args.pair.resolve()
release = json.loads((Path(__file__).parent / "release.json").read_bytes())
sys.path.insert(0, str(Path(__file__).resolve().parent))
from role_integrity import verify_role

for role in ("mkm", "kmc"):
    root = pair / role
    if json.loads((root / "release-identity.json").read_bytes()) != {
            "role": role, "versions": release["role_versions"]}:
        raise ValueError(f"Different {role} release")
    verify_role(root, release["role_versions"][role])
sys.path.insert(0, str(pair / "kmc"))
from scripts.kinetic_data.result_comparison import compare

print(json.dumps(compare(args.request, args.sha256, mkm_worktree=pair / "mkm"), indent=2, allow_nan=False))
