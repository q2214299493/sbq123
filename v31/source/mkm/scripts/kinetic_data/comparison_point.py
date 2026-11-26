"""Export a freshly replayed CATKINAS point for offline cross-engine comparison."""
import argparse
import json
from pathlib import Path

from scripts.baseline_mkm.rate_adapter import adapt
from scripts.baseline_mkm.result_binding import bind_result
from scripts.kinetic_data.native_rate_output import require
from scripts.kinetic_data.scientific_identity import read_artifact
from scripts.rate_output_v2 import validate_network_bound_rate_output


def export_point(run, root):
    run = Path(run).resolve()
    binding = bind_result(run)
    plan, _ = read_artifact(run / "plan.json")
    require(binding["profile_bound_by_plan"], "Comparison requires a plan-bound physical reference")
    rates, qualification = adapt(
        run / "ACCEPTED.json", network_path=run / "network.json", dataset_path=run / "dataset.json",
        config_path=run / "configuration.json", input_path=run / "input" / "INPUT_phase25.m",
        normalization_path=plan["normalization_profile"], root=root)
    validate_network_bound_rate_output(rates, run / "network.json")
    require(qualification["receipt"]["sha256"] == binding["execution"]["receipt_sha256"]
            and qualification["result_record"]["sha256"] == binding["execution"]["result_sha256"],
            "MKM result changed during replay")
    return dict(binding=binding, rate_output=rates, observations=qualification["single_point_replay"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    print(json.dumps(export_point(args.run, Path.cwd()), allow_nan=False))
