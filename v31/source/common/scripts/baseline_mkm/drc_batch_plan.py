"""Plan a bounded batch against one immutable network, reusing verified native DRC evidence."""

from pathlib import Path

from scripts.artifact_io import load_json_object as read, sha256_file, sha256_json
from scripts.baseline_mkm import drc_pair as pair
from scripts.baseline_mkm.drc_report import compare
from scripts.baseline_mkm.drc_step_size import validation
from scripts.baseline_mkm.kinetic_analysis import indexed
from scripts.baseline_mkm.ts_perturbation import HALF_STEP_EV, reviewed_reaction
from scripts.kinetic_parameters.engine import check_version
from scripts.kinetic_parameters.laws import pressure_unit

LIMITS = dict(max_runs=4, per_run_s=210, native_s=840, wall_s=960, max_parallel=1, max_retries=0)


def eligibility(network, dataset, entry, row):
    if row is None:
        return "UNAVAILABLE", ["Kinetic dataset lacks this reaction"]
    if not row["export_eligible"] or row["missing"]:
        return "BLOCKED", list(row["missing"]) or ["Not eligible for kinetic export"]
    if entry["direction"]["status"] != "reversible":
        return "REQUIRES_REVIEW", ["Reviewed reversible forward and reverse laws required"]
    if not all(row["rates"].get(k) for k in ("forward", "reverse")):
        return "UNAVAILABLE", ["Missing directional rate law"]
    try:
        reviewed_reaction(network, dataset, row["reaction_id"])
    except (ValueError, KeyError, TypeError) as error:
        return "REQUIRES_REVIEW", [str(error)]
    return "READY", []


def scan(network, dataset):
    check_version(network, "network_version")
    check_version(dataset, "dataset_version")
    if network["network_version"] != dataset["network_version"]:
        raise ValueError("Different parent network version")
    rows = indexed(dataset["reactions"], "reaction_id")
    candidates = {}
    for entry in network["reactions"]:
        definition = entry["definition"]
        rid = definition["reaction_id"]
        if rid in candidates:
            raise ValueError(f"Duplicate network reaction ID: {rid}")
        row = rows.get(rid)
        status, gaps = eligibility(network, dataset, entry, row)
        rates = (row or {}).get("rates", {})
        orders = {side: (rate["gas_orders"] if rate else None) for side, rate in rates.items()}
        candidates[rid] = dict(
            status=status,
            missing=gaps,
            drc=None,
            stability="unavailable",
            reaction_type=definition["reaction_type"],
            equation=entry["direction"]["forward"],
            reversibility=entry["direction"]["status"],
            ts_id=definition.get("ts_id"),
            ts_review=entry.get("ts_review"),
            energies=entry["energies"],
            energy_reference_id=definition.get("energy_reference_id"),
            rate_law_id=definition.get("rate_law_id"),
            gas_orders=orders,
            coefficient_units={s: pressure_unit(sum(o.values()), "bar") if o is not None else None for s, o in orders.items()},
            parameter_set_id=((row or {}).get("parameter_set") or {}).get("parameter_set_id"),
        )
    if rows.keys() - candidates.keys():
        raise ValueError("Kinetic dataset contains reactions outside network")
    return candidates


def reuse(base, rid, source):
    reconstructed = {}
    hashes = {}
    for size in ("coarse", "fine"):
        artifact = Path(source[size]["report"])
        hashes[size] = sha256_file(artifact)
        if hashes[size] != source[size]["sha256"]:
            raise ValueError(f"{rid}: changed {size} report hash")
        result = compare(Path(source[size]["pair"]).resolve(), base)
        if result["reaction_id"] != rid:
            raise ValueError("Wrong reaction in reuse evidence")
        reconstructed[size] = result
    validation_record = validation(reconstructed["coarse"], reconstructed["fine"], hashes["coarse"])
    reconstructed["fine"]["step_size_validation"] = validation_record
    if any(value != read(Path(source[size]["report"])) for size, value in reconstructed.items()):
        raise ValueError(f"{rid}: archived report differs from verified native runs")
    return reconstructed["fine"]


def prepare(root, base, sources):
    receipt, analysis = pair.baseline(base)
    network, dataset = (read(base / (key + ".json")) for key in ("network", "dataset"))
    candidates = scan(network, dataset)
    if sources.keys() - candidates.keys():
        raise ValueError("Reuse source belongs to a different network")
    for rid, source in sources.items():
        row = candidates[rid]
        if row["status"] != "READY":
            raise ValueError("Unqualified reaction supplied as reusable evidence")
        result = reuse(base, rid, source)
        stable = result["step_size_validation"]["passed"]
        row.update(
            status="ALREADY_VALIDATED" if stable else "REQUIRES_REVIEW",
            drc=result["drc"],
            stability="stable" if stable else "unstable",
            missing=[] if stable else ["Step-size refinement required"],
        )
    ready = [rid for rid, row in candidates.items() if row["status"] == "READY"]
    if 2 * len(ready) > LIMITS["max_runs"]:
        raise ValueError("Eligible runs exceed bounded pilot capacity; select a separately reviewed scope")
    jobs = {}
    for i, rid in enumerate(ready):
        directory = f"pair-{i + 1}"
        plan = pair.prepare(root / directory, base, HALF_STEP_EV, rid)
        jobs[rid] = dict(directory=directory, pair_sha256=sha256_json(plan), members=plan["members"])
    root.mkdir(parents=True, exist_ok=True)
    manifest = dict(
        format="bounded-drc-plan/1",
        limits=LIMITS,
        network_version=network["network_version"],
        dataset_version=dataset["dataset_version"],
        baseline_hashes=analysis["source_hashes"],
        baseline_run_id=receipt["run_id"],
        temperature_K=analysis["temperature_K"],
        partial_pressures_bar=analysis["partial_pressures_bar"],
        normalization=analysis["normalization"],
        observable="positive net overall turnovers per reference site pair per second",
        candidates=candidates,
        reuse_sources=sources,
        jobs=jobs,
    )
    pair.put(root / "batch-plan.json", manifest)
    return manifest
