"""Independent byte/label/control-design checks; no model,submission or training."""
import json
import xml.etree.ElementTree as ET

import numpy as np
from ase.db import connect

from scripts.artifact_io import sha256_file, write_json_exclusive

from .prepare import DBS, MANIFEST_SHA, OUTPUT, POOL, ROOT


def main():
    request_path = OUTPUT / "comparison_request.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    assert request["training_authorized"] is False and request["GPU_submitted"] is False
    assert request["total_GPU_walltime_minutes_cap"] == 60 and request["total_optimizer_steps_cap"] == 992
    assert sha256_file(POOL / "training_manifest.json") == MANIFEST_SHA
    original = json.loads((POOL / "training_manifest.json").read_text(encoding="utf-8"))
    for source in request["source_files"]:
        assert sha256_file(ROOT / source["path"]) == source["sha256"]
    manifests, configs = {}, {}
    import yaml
    for arm, binding in request["arms"].items():
        root = OUTPUT / arm
        path = OUTPUT / binding["path"]
        assert sha256_file(path) == binding["sha256"]
        document = json.loads(path.read_text(encoding="utf-8"))
        assert document["training_authorized"] is False
        for item in document["artifacts"]:
            assert sha256_file(root / item["path"]) == item["sha256"], item["path"]
        assert not (root / "heldout.db").exists() and not (root / "output").exists()
        manifests[arm] = json.loads((root / "training_manifest.json").read_text(encoding="utf-8"))
        configs[arm] = yaml.safe_load((root / "config.yml").read_text(encoding="utf-8"))
        for name in ("development.db", "development_metadata.npz"):
            assert sha256_file(root / name) == sha256_file(DBS / name)
    assert (OUTPUT / "treatment/training_manifest.json").read_bytes() == (POOL / "training_manifest.json").read_bytes()
    control = manifests["control"]
    for key in original:
        if key != "splits":
            assert control[key] == original[key]
    assert control["splits"]["development"] == original["splits"]["development"]
    assert control["splits"]["heldout"] == original["splits"]["heldout"]
    allowed = {"proposed_per_atom_loss_weights", "proposed_source_stage_sampling_probability"}
    for row, source in zip(control["splits"]["train"], original["splits"]["train"], strict=True):
        assert set(row) == set(source)
        assert {k: v for k, v in row.items() if k not in allowed} == {k: v for k, v in source.items() if k not in allowed}
        free = sorted(set(range(len(row["symbols"]))) - set(row["fixed_atom_indices_0based"]))
        np.testing.assert_array_equal(np.asarray(row["proposed_per_atom_loss_weights"])[free], np.full(len(free), 1./len(free)))
        assert row["proposed_source_stage_sampling_probability"] == 1./248
    left, right = configs.values()
    for config in (left, right):
        for key in ("train", "val"):
            config["dataset"][key]["src"] = "<same_split_db>"
            config["dataset"][key]["metadata_path"] = "<same_split_metadata>"
    assert left == right, "training config differs beyond package locations"
    for rows in zip(connect(OUTPUT / "control/train.db").select(), connect(OUTPUT / "treatment/train.db").select(), strict=True):
        a, b = [row.toatoms() for row in rows]
        np.testing.assert_array_equal(a.positions, b.positions)
        np.testing.assert_array_equal(a.get_forces(apply_constraint=False), b.get_forces(apply_constraint=False))
        assert rows[0].data.sid == rows[1].data.sid
    native = json.loads((OUTPUT / "native_cli.json").read_text())
    assert native["status"] == "PASS_NATIVE_CLI_RAM_ONLY" and not native["CUDA_initialized"]
    assert native["on_disk_deployment_namespace_verified"] is False
    receipt = json.loads((OUTPUT / "native_cli_receipt.json").read_text())
    assert receipt["exit_code"] == 0
    for arm in ("control", "treatment"):
        root = OUTPUT / arm
        assert sha256_file(root / "config.yml") == receipt["config_sha256"][arm]
        for name, sha in receipt["runtime_sha256"].items():
            assert sha256_file(root / "runtime/scripts/adsorption" / (name + ".py")) == sha
    tests = ET.parse(OUTPUT / "scoped_tests.xml").getroot().findall("testsuite")
    counts = {key: sum(int(suite.attrib[key]) for suite in tests) for key in ("tests", "failures", "errors", "skipped")}
    assert counts == {"tests": 137, "failures": 0, "errors": 0, "skipped": 0}
    result = {"status": "PASS_PACKAGE_REVIEW_NO_GPU", "request_sha256": sha256_file(request_path),
        "tests": counts, "both_arms_hash_verified": True, "original_pool_unchanged": True,
        "control_changes_train_weights_and_probabilities_only": True,
        "identical_development_records_and_selection_config": True,
        "raw_training_geometry_forces_identical_between_arms": True,
        "heldout_integrity_only_no_model_use": True, "GPU_run_or_upload": False,
        "native_CLI_check": "deployed_parser_registry_with_RAM_modules_not_on_disk_deployment",
        "remaining": ["user review and exact-hash authorization", "authorized deployment/on-disk native/checkpoint/GPU/scheduler preflight",
            "full model AMP/optimizer behavior", "scientific force/geometry/paired VASP speedup evaluation"],
        "evidence": [{"path": path.relative_to(ROOT).as_posix(), "sha256": sha256_file(path)} for path in
            [request_path, OUTPUT / "scoped_tests.xml", OUTPUT / "native_cli.json", OUTPUT / "native_cli_receipt.json",
             OUTPUT / "native_cadence.json", OUTPUT / "native_cadence_receipt.json"]]}
    write_json_exclusive(OUTPUT / "verification_receipt.json", result)
    print(json.dumps({"status": result["status"], "tests": counts, "request_sha256": result["request_sha256"]}))


if __name__ == "__main__":
    main()
