"""Compare complete, verified pairs on one observable and retain incomplete reaction rows."""

from datetime import datetime

from scripts.artifact_io import load_json_object as read, sha256_file, sha256_json
from scripts.baseline_mkm import drc_pair_records as pair
from scripts.baseline_mkm.drc_batch_plan import LIMITS, reuse, scan
from scripts.baseline_mkm.drc_report import archive_members, compare, write_once
from scripts.baseline_mkm.drc_step_size import summarize
from scripts.baseline_mkm.single_point_result import check_close
from scripts.baseline_mkm.ts_perturbation import HALF_STEP_EV


def describe(result, manifest):
    base = result["cases"]["baseline"]
    if (
        base["source_hashes"] != manifest["baseline_hashes"]
        or base["dataset_version"] != manifest["dataset_version"]
        or base["network_version"] != manifest["network_version"]
        or result["delta_eV"] != HALF_STEP_EV
        or any(result[k] != manifest[k] for k in ("temperature_K", "partial_pressures_bar", "normalization", "observable"))
    ):
        raise ValueError("Different batch baseline, conditions, observable or displacement")
    summary = summarize(result)
    v = result.get("step_size_validation")
    stable = "untested" if v is None else "stable" if v["passed"] else "unstable"
    response = result["changes_from_baseline"]
    diagnostics = None
    if result["outside_zero_to_one"]:
        diagnostics = dict(
            reason="Signed response outside [0,1]; inspect inhibition or amplification",
            one_sided_gap=abs(summary["positive_side"] - summary["negative_side"]),
            coverage_and_flux_changes=response,
        )
    return dict(
        drc=summary["central"],
        positive_side=summary["positive_side"],
        negative_side=summary["negative_side"],
        delta_eV=result["delta_eV"],
        stability=stable,
        numerical_uncertainty=dict(
            standard_error=None,
            reason="No repeated independent numerical estimates",
            one_sided_gap=abs(summary["positive_side"] - summary["negative_side"]),
            observed_step_change=v["absolute_difference"] if v else None,
        ),
        coarse_drc=v["coarse"]["central"] if v else None,
        tolerance=v["tolerance"] if v else None,
        tof={k: c["net_tof_per_site_pair_s"] for k, c in result["cases"].items()},
        scientific_validation=summary["residuals"],
        diagnostics=diagnostics,
        missing=[] if stable == "stable" else ["Independent step-size stability confirmation required"],
    )


def ranking(rows):
    valid = [rid for rid, row in rows.items() if row.get("scientific_validation") and row["stability"] == "stable"]
    return [{"reaction_id": rid, "drc": rows[rid]["drc"]} for rid in sorted(valid, key=lambda rid: (-rows[rid]["drc"], rid))]


def inspect_pair(directory, base, rid, job):
    plan = read(directory / "pair.json")
    if plan["reaction_id"] != rid or sha256_json(plan) != job["pair_sha256"] or plan["members"] != job["members"]:
        raise ValueError("Pair identity differs from batch")
    actual = {}
    for label, sign in pair.SIGNS:
        run = pair.check_member(directory, base, label, sign)
        actual[label] = dict(run_id=run.name, stage=pair.point.status(run)["stage"], invoked=(run / "RUNNING.json").exists(), native_s=None)
        if (run / "ACCEPTED.json").exists():
            pair.accepted(run)
            stamps = [datetime.fromisoformat(read(run / f"{k}.json")["timestamp"]) for k in ("RUNNING", "COLLECTING")]
            actual[label]["native_s"] = (stamps[1] - stamps[0]).total_seconds()
    return actual


def render(report):
    rows = report["reactions"]
    lines = [
        "# Network DRC pilot",
        "",
        "All TOFs are positive net overall turnovers per reference site pair per second.",
        "",
        "| Reaction | TS | Forward / reverse barrier (eV) | Source | Baseline / plus / minus TOF | DRC | Stability |",
        "|---|---|---|---|---|---:|---|",
    ]
    for rid, row in rows.items():
        barriers = row["energies"]["gibbs_ev"]
        tofs = row.get("tof", {})
        values = " / ".join(f"{tofs[k]:.8g}" for k in ("baseline", "plus", "minus")) if tofs else "unavailable"
        value = f"{row['drc']:.9g}" if row["drc"] is not None else "unavailable"
        lines.append(
            f"| {rid} | {row['ts_id']} | {barriers['forward']} / {barriers['reverse']} | "
            f"{row['origin']} | {values} | {value} | {row['stability']} |"
        )
    lines += ["", "## Ranked, step-size-stable results", ""]
    lines.extend(f"{i}. {item['reaction_id']} — {item['drc']:.9g}" for i, item in enumerate(report["ranking"], 1))
    lines += ["", "## Missing evidence and scope", ""]
    for rid, row in rows.items():
        if row["missing"]:
            lines.append(f"- {rid}: " + ", ".join(row["missing"]))
        if row.get("diagnostics"):
            lines.append(f"- {rid}: {row['diagnostics']['reason']}. See the one-sided slopes and response matrices.")
    limits = report["budget"]["limits"]
    lines += [
        "",
        "## Execution budget",
        "",
        f"Native invocations: {report['budget']['actual_native_runs']} of {limits['max_runs']}. "
        f"Measured native seconds: {report['budget']['native_s']}. Batch wall seconds: {report['budget']['wall_s']}.",
        "",
        "## Response matrices",
        "",
        "Changes are relative to the common baseline. Coverage and site utilization are fractions. "
        "Elementary flux changes are events per reference site pair per second.",
        "",
        "| Perturbed TS | Sign | Quantity | Species, site or step | Change |",
        "|---|---|---|---|---:|",
    ]
    for rid, changes in report["coverage_response"].items():
        for side, factors in changes.items():
            for quantity, values in factors.items():
                for subject, value in values.items():
                    lines.append(f"| {rid} | {side} | {quantity} | {subject} | {value:.9g} |")
            for reaction, values in report["flux_response"][rid][side].items():
                for direction, value in values.items():
                    lines.append(f"| {rid} | {side} | {direction} | {reaction} | {value:.9g} |")
    return "\n".join(lines) + "\n"


def publish(root, base, output):
    manifest = read(root / "batch-plan.json")
    _, analysis = pair.baseline(base)
    if manifest["baseline_hashes"] != analysis["source_hashes"] or manifest["limits"] != LIMITS:
        raise ValueError("Stale baseline or batch budget")
    rows = scan(read(base / "network.json"), read(base / "dataset.json"))
    expected = {rid for rid, row in rows.items() if row["status"] == "READY"}
    reused, planned = set(manifest["reuse_sources"]), set(manifest["jobs"])
    if set(rows) != set(manifest["candidates"]) or (reused | planned) != expected or reused & planned:
        raise ValueError("Changed batch reaction inventory")
    runs, coverage, flux, provenance = {}, {}, {}, {}
    output.mkdir(exist_ok=True, parents=True)
    for rid, row in rows.items():
        if rid in manifest["reuse_sources"]:
            result = reuse(base, rid, manifest["reuse_sources"][rid])
            row["origin"] = "reused"
            provenance[rid] = manifest["reuse_sources"][rid]
        elif rid in manifest["jobs"]:
            job = manifest["jobs"][rid]
            directory = root / job["directory"]
            runs[rid] = inspect_pair(directory, base, rid, job)
            if (directory / "failed.json").exists() or not (directory / "finished.json").exists():
                row.update(origin="incomplete", missing=["No accepted complete signed pair"], stability="unavailable")
                continue
            result = compare(directory, base)
            target = output / job["directory"]
            target.mkdir(exist_ok=True)
            pair.put(target / "pair-result.json", result)
            archive_members(directory, base, target, rid)
            provenance[rid] = dict(
                pair_result_sha256=sha256_file(target / "pair-result.json"),
                members=job["members"],
                result_path=job["directory"] + "/pair-result.json",
            )
            row["origin"] = "new"
        else:
            row["origin"] = "excluded"
            continue
        if result["reaction_id"] != rid:
            raise ValueError("Different reaction in batch result")
        row.update(describe(result, manifest))
        row["status"] = manifest["candidates"][rid]["status"]
        changes = result["changes_from_baseline"]
        coverage[rid] = {
            label: dict(coverage=v["coverage"], vacancies=v["vacancies"], occupied={s: -x for s, x in v["vacancies"].items()})
            for label, v in changes.items()
        }
        flux[rid] = {label: v["flux"] for label, v in changes.items()}
    finish = read(root / "finished.json") if (root / "finished.json").exists() else None
    if finish and (
        finish["pairs_sha256"] != sha256_json(manifest)
        or not 0 <= finish["elapsed_s"] <= LIMITS["wall_s"]
        or any(rows[rid]["origin"] != "new" for rid in manifest["jobs"])
    ):
        raise ValueError("Invalid batch completion")
    members = [m for job in runs.values() for m in job.values() if m["invoked"]]
    known = [m["native_s"] for m in members if m["native_s"] is not None]
    if len(members) > LIMITS["max_runs"] or sum(known) > LIMITS["native_s"] or any(not 0 <= t <= LIMITS["per_run_s"] for t in known):
        raise ValueError("Native budget exceeded")
    for rid in coverage:
        check_close(rows[rid]["tof"]["baseline"], analysis["tof"]["overall"]["per_site_pair_s"], "shared baseline TOF")
    result = dict(
        format="bounded-drc-batch/1",
        complete=bool(finish) or not manifest["jobs"],
        plan_sha256=sha256_json(manifest),
        reactions=rows,
        ranking=ranking(rows),
        unavailable=[r for r, v in rows.items() if v["drc"] is None],
        blocked=[r for r, v in rows.items() if v["status"] == "BLOCKED"],
        coverage_response=coverage,
        flux_response=flux,
        budget=dict(
            limits=LIMITS,
            members=runs,
            actual_native_runs=len(members),
            native_s=sum(known) if len(known) == len(members) else None,
            wall_s=finish["elapsed_s"] if finish else None,
        ),
        provenance=provenance,
    )
    pair.put(output / "result.json", result)
    write_once(output / "network_report.md", render(result).encode())
    write_once(output / "batch-plan.json", (root / "batch-plan.json").read_bytes())
    return result
