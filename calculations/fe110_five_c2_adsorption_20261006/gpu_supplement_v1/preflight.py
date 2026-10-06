"""Verify frozen files and ASE input loading without running an ML model."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "runtime"))
from artifact_io import sha256_file
from aqcat25_handoff import validate_handoff
from relax_endpoint_candidates import load_candidate


def main():
    batch = json.loads((ROOT / "batch_manifest.json").read_text(encoding="utf-8"))
    for item in batch["files"]:
        assert sha256_file(ROOT / item["path"]) == item["sha256"], item["path"]
    checkpoint = Path("/home/sbq/sbq/aqcat25/demo_single/model.pt")
    assert sha256_file(checkpoint) == batch["checkpoint_sha256"]
    for item in batch["handoffs"]:
        directory = ROOT / item["name"]
        assert sha256_file(directory / "handoff.json") == item["handoff_sha256"]
        validate_handoff(directory / "handoff.json", root=directory,
                         schema_path=ROOT / "runtime/aqcat25_handoff.schema.json")
        document, atoms = load_candidate(directory / "handoff.json")
        assert len(atoms) in (48, 49)
        assert document["model"]["max_steps"] == 80
        assert not (directory / "output").exists(), "refuse duplicate execution"
    print(json.dumps({"status": "GPU_BEFORE_EXECUTION_PASS_NO_MODEL_RUN", "candidates": len(batch["handoffs"])}))


if __name__ == "__main__":
    main()
