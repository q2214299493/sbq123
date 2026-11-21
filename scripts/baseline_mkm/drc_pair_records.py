"""Read, verify and immutably publish DRC pair records without execution orchestration."""

from pathlib import Path

from scripts.artifact_io import load_json_object as read, sha256_file, sha256_json, write_json_exclusive as save
from scripts.baseline_mkm import analysis, single_point as point
from scripts.baseline_mkm.ts_perturbation import DELTA_EV, PARENT, REACTION, derivative
from scripts.baseline_mkm.sensitivity_inputs import derive
from scripts.execution_permission import require_bound_action
from scripts.scientific_validation import finite_number

REPORTS = Path(__file__).resolve().parents[2] / "reports/multiphase"
OPTIONS = REPORTS / "phase3_1/benchmark_normalization.json"
BUDGET = 480
SIGNS = (("plus", 1), ("minus", -1))


def accepted(run):
    receipt = point.status(run)
    if receipt["stage"] != "ACCEPTED":
        raise ValueError(f"{run.name}: expected accepted point, found {receipt['stage']}")
    plan = read(run / "plan.json")
    decision = read(run / "approval.json")
    receipt["raw_plan_sha256"] = sha256_json(plan)
    require_bound_action(decision, point.ACTION, receipt["raw_plan_sha256"], {point.ACTION})
    if (
        decision["DECISION"] != "approve"
        or decision["question_id"] != plan["question_id"]
        or not decision["reviewer"]
        or sha256_json(decision) != receipt["approval_reference"]
        or sha256_file(Path(decision["source"]["path"])) != decision["source"]["sha256"]
    ):
        raise ValueError("Changed approval binding")
    for path, digest in receipt["output_hashes"].items():
        if sha256_file(run / path) != digest:
            raise ValueError(f"Changed native evidence: {path}")
    a = analysis.analyze(*(run / (k + ".json") for k in ("network", "dataset", "configuration", "result")), receipt, OPTIONS)
    finite_number(a["tof"]["overall"]["per_site_pair_s"], "positive overall net TOF per site pair", positive=True)
    return receipt, a


def baseline(run):
    receipt, report = accepted(run)
    reference = read(REPORTS / "phase3_0/benchmark_manifest.json")
    for key in (
        "raw_plan_sha256",
        "result_sha256",
        "approval_reference",
        "network_version_id",
        "input_hashes",
        "kinetic_dataset_version",
        "run_id",
        "output_hashes",
    ):
        if receipt[key] != reference[key]:
            raise ValueError(f"Baseline differs from accepted benchmark: {key}")
    if receipt["kinetic_dataset_version"] != PARENT or report != read(REPORTS / "phase3_1/closed_cycle/analysis.json"):
        raise ValueError("Baseline kinetic analysis differs from accepted benchmark")
    return receipt, report


def expected(base, sign, delta_eV=DELTA_EV, reaction_id=REACTION):
    n, d, c = (read(base / (k + ".json")) for k in ("network", "dataset", "configuration"))
    child = derivative(n, d, sign, delta_eV, reaction_id)
    return child, dict(c, dataset_version=child["dataset_version"])


def put(path, data):
    if path.exists():
        if read(path) != data:
            raise ValueError(f"Conflicting immutable artifact: {path}")
    else:
        save(path, data)


def planned_inputs(base, sign, selection):
    if "sensitivity" in selection:
        inputs = (read(base / (key + ".json")) for key in ("network", "dataset", "configuration"))
        return derive(*inputs, selection["sensitivity"], sign)
    return expected(base, sign, selection["delta_eV"], selection.get("reaction_id", REACTION))


def check_member(root, base, label, sign):
    pair = read(root / "pair.json")
    child, config = planned_inputs(base, sign, pair)
    run = root / (label + "-" + child["dataset_version"][:16])
    plan = read(run / "plan.json")
    member = pair["members"][label]
    if member != {"run_id": run.name, "plan_sha256": sha256_json(plan)}:
        raise ValueError("Changed perturbation plan identity")
    if read(run / "dataset.json") != child or read(run / "configuration.json") != config:
        raise ValueError("Changed perturbation dataset or conditions")
    original = read(base / "plan.json")
    if "sensitivity" in pair and pair["sensitivity"]["kind"] == "gas_order":
        original = dict(original, partial_pressures_bar=config["partial_pressure_bar"], total_pressure_bar=config["total_pressure_bar"])
    for key in (
        "question_id",
        "ticket_id",
        "runtime",
        "temperature_K",
        "partial_pressures_bar",
        "total_pressure_bar",
        "use_scope",
        "standard_states",
        "site_inventory",
        "initial_coverages",
        "solver_settings",
        "network_version_id",
    ):
        if plan[key] != original[key]:
            raise ValueError(f"Incompatible pair condition: {key}")
    if plan["input_hashes"]["network"] != original["input_hashes"]["network"]:
        raise ValueError("Changed original network bytes")
    return run


def verified_finish(root, manifest):
    finished = read(root / "finished.json")
    elapsed = finite_number(finished["elapsed_s"], "pair elapsed seconds", positive=True)
    remaining = finite_number(finished["remaining_s"], "remaining budget", nonnegative=True)
    if (
        (root / "failed.json").exists()
        or finished["pair_sha256"] != sha256_json(manifest)
        or elapsed > BUDGET
        or abs(remaining - (BUDGET - elapsed)) > 1e-6
    ):
        raise ValueError("No valid completed pair within the budget")
    return finished
