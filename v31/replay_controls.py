"""Replay sealed Ni/Cu and Zacros controls, with native launch and old mount access disabled."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("pair", type=Path)
parser.add_argument("role", choices=["mkm", "kmc"])
args = parser.parse_args()
if not sys.flags.isolated or not sys.dont_write_bytecode:
    parser.error("Run with python -I -B")
root = args.pair.resolve() / args.role
release = json.loads((Path(__file__).parent / "release.json").read_bytes())
sys.path.insert(0, str(Path(__file__).resolve().parent))
from role_integrity import verify_role

verify_role(root, release["role_versions"][args.role])
sys.path.insert(0, str(root))
origins = [Path(k) for k in json.loads((root / "evidence-mounts.json").read_bytes())]


def guard(event, values):
    if event == "subprocess.Popen" or event == "os.system":
        raise RuntimeError("Replay cannot launch external programs")
    if event == "open" and isinstance(values[0], (str, os.PathLike)):
        path = Path(values[0]).absolute()
        if any(path.is_relative_to(k) for k in origins):
            raise RuntimeError(f"Unexpected original-location read: {path}")


sys.addaudithook(guard)
os.chdir(root)


def read(path):
    return json.loads(path.read_bytes())


if args.role == "mkm":
    from scripts.kinetic_data.comparison_point import export_point

    run = root / "reports/workflow_development/stage_v2_4_4_step3/nicu-400k-001"
    actual = export_point(run, root)
    expected = read(root.parent / "kmc/reports/workflow_development/stage_v3_1_step1_identity_binding/mkm-point.json")
    if actual["binding"] != expected:
        raise ValueError("Historical Ni/Cu binding differs")
    result = read(run / "result.json")
    report = dict(binding_sha256=expected["binding_sha256"], pair_tof_s=result["tof_s_inverse"],
                  individual_site_tof_s=result["mean_tof_per_individual_site_s"])
else:
    from scripts.surface_kmc.study import replay

    stage = root / "reports/workflow_development/stage_v3_0_0_kmc_step3"
    index = read(stage / "final-qualification/native-evidence-index.json")
    report = []
    # The first local writer freezes the common control for the split and uninterrupted recordings.
    for row in index["records"]:
        case = root / row["evidence_directory"]
        run = root / row["run_directory"]
        # The archived writer-only stage has no execution receipt.
        status = row.get("receipt_status") if row["native_launches"] == 0 else row["receipt_status"]
        record = {"case": case.name, "historical_launches": row["native_launches"],
                  "original_receipt_status": status}
        for name, expected in row["all_run_file_hashes"].items():
            if hashlib.sha256((run / name).read_bytes()).hexdigest() != expected:
                raise ValueError(f"Changed historical output {run.name}/{name}")
        if status == "validated_output":
            model = case if (case / "dataset.json").is_file() else stage / "02-local-writer"
            series = replay(read(model / "dataset.json"), read(model / "configuration.json"), run)
            if series["seed"] != row["seed"] or series["trajectory"]["terminal_step"] != row["terminal_events"]:
                raise ValueError(f"Replay differs from archived terminal state: {case.name}")
            record.update(seed=series["seed"], terminal_step=series["trajectory"]["terminal_step"],
                          terminal_time_s=series["trajectory"]["terminal_time_s"])
        report.append(record)
print(json.dumps(report, indent=2, allow_nan=False))
