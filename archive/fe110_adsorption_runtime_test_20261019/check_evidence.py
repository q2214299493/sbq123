"""Independent bounded verification of saved local/native CPU test evidence."""
import json
import math
import xml.etree.ElementTree as ET

from scripts.artifact_io import sha256_file, write_json_exclusive

from .local_smoke import EXPECTED, MANIFEST
from .probe_runtime import OUTPUT, ROOT


def main():
    assert sha256_file(MANIFEST) == EXPECTED
    local = json.loads((OUTPUT / "local_smoke_receipt.json").read_bytes())
    native = json.loads((OUTPUT / "native_cpu_smoke_4.json").read_bytes())
    receipt = json.loads((OUTPUT / "native_cpu_smoke_4.receipt.json").read_bytes())
    suites = list(ET.parse(OUTPUT / "final_scoped_tests.xml").getroot().iter("testsuite"))
    tests = sum(int(s.attrib["tests"]) for s in suites)
    assert tests == 124 and all(s.attrib["failures"] == s.attrib["errors"] == s.attrib["skipped"] == "0" for s in suites)
    assert receipt["exit_code"] == 0
    assert receipt["stdout_sha256"] == sha256_file(OUTPUT / "native_cpu_smoke_4.json")
    for relative, expected in receipt["source_hashes"].items():
        assert sha256_file(ROOT / relative) == expected
    for artifact in local["artifacts"]:
        assert sha256_file(OUTPUT / artifact["path"]) == artifact["sha256"]
    assert local["counts"] == {"train": 248, "development": 60}
    assert abs(local["expected_and_actual_loss_eV_A"] - .02 * math.sqrt(3)) < 1e-12
    assert abs(native["normalized_loss"] - .1 * math.sqrt(3)) < 1e-6
    assert abs(native["physical_role_metric_eV_A"] - .1 * math.sqrt(3) * 2.887317180633545) < 1e-6
    assert native["registry_class_path_selected"] and native["sampler_resume_exact"] and native["fixed_gradients_zero"]
    assert native["CPU_amp_force_dtypes_tested"] == ["float16", "bfloat16"]
    assert not native["model_instantiated"] and not native["GPU_used"] and not native["training_performed"]
    result = {"status": "PASS_VERIFIED_ADAPTER_CPU_TESTS_NOT_MODEL_VALIDATION", "tests_passed": tests,
        "real_data_database_roundtrip": local["counts"], "native_framework_fixture_graphs": {"train": 3, "validation": 3},
        "original_pool_unchanged_sha256": EXPECTED, "native_runtime_sources_match_current": True,
        "model_accuracy_or_acceleration_proved": False, "GPU_training_authorized_or_run": False,
        "evidence_hashes": {name: sha256_file(OUTPUT / name) for name in ("local_smoke_receipt.json",
            "native_cpu_smoke_4.json", "native_cpu_smoke_4.receipt.json", "final_scoped_tests.xml")}}
    write_json_exclusive(OUTPUT / "verification_receipt.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
