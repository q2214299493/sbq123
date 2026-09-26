"""Verify a deployed GPU package without loading or running either model."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from artifact_io import sha256_file
from dual_model_ml_neb import _assert_geometry_guards, _load_images, _load_request, _verify_checkpoint


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    root = args.request.resolve().parent
    if sha256_file(args.request) != args.expected_sha256:
        raise ValueError("Request changed after work-side review")
    request = _load_request(args.request)
    for folder, entries in ((root / "runtime", request["runtime_bindings"]),
                            (root, request["source_evidence_files"])):
        for relative, expected in entries.items():
            target = (folder / relative).resolve()
            if not target.is_relative_to(root) or sha256_file(target) != expected:
                raise ValueError(f"Changed or escaped payload: {relative}")
    for role in ("primary", "secondary"):
        model = request["models"][role]
        _verify_checkpoint(Path(model["remote_checkpoint_path"]), model["checkpoint_sha256"], role)
    images = _load_images(request, root)
    _assert_geometry_guards(images, request, "remote_preflight",
                            monitored_guard_policy=request["ordinary_ml_neb"]["monitored_geometry_guard"])
    if request["preconditioning"]["enabled"] or request["restraint_release"]["stages"]:
        raise ValueError("This authorized run must have no extra restraints")
    print(json.dumps({"status": "PASS", "request_sha256": args.expected_sha256,
                      "image_count": len(images), "runtime_and_checkpoint_hashes": "PASS",
                      "model_executed": False, "submitted": False}))


if __name__ == "__main__":
    main()
