"""Read-only comparison of a replayed MKM point and an event-complete KMC window."""
import argparse
import json
import math
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

from scripts.artifact_io import sha256_file, sha256_json
from scripts.kinetic_data.comparison_observables import difference, measure
from scripts.kinetic_data.native_rate_output import require
from scripts.kinetic_data.scientific_identity import IncompatibleIdentity, read_artifact, require_common_identities
from scripts.kinetic_parameters.engine import reviewed
from scripts.runtime_resources import SOURCE_ROOT
from scripts.surface_kmc.window_bridge import bridge


def _pinned(directory, ref):
    path = directory / ref["path"]
    require(sha256_file(path) == ref["sha256"], f"Changed evidence: {path.name}")
    return path


def _dataset(path, digest):
    dataset, actual = read_artifact(path)
    require(actual == digest, "Dataset bytes changed after replay")
    return dataset


def _point(request, directory, mkm_worktree):
    run = (directory / request["run"]).resolve()
    # The caller chooses the trusted MKM installation independently of the data manifest.
    process = subprocess.run([sys.executable, "-B", "-m", "scripts.kinetic_data.comparison_point", str(run)],
                             cwd=mkm_worktree, capture_output=True, text=True, timeout=120, check=False)
    if process.returncode:
        reason = process.stderr.strip().splitlines()
        raise ValueError("MKM replay failed: " + (reason[-1] if reason else str(process.returncode)))
    point = json.loads(process.stdout)
    b = point["binding"]
    require(b["binding_sha256"] == request["binding_sha256"], "Different MKM execution/root binding")
    return point, _dataset(run / "dataset.json", b["dataset"]["file_sha256"])


def _window(ref, directory):
    path = _pinned(directory, ref)
    record = bridge(path, ref["sha256"], allow_partial_mapping=True)
    manifest, digest = read_artifact(path)
    require(digest == ref["sha256"], "Window manifest changed during replay")
    dataset = _dataset(path.parent / manifest["artifacts"]["dataset"]["path"], record["window"]["dataset"]["file_sha256"])
    return record, dataset


def _evidence(record, mkm):
    if record is None:
        return None
    rates = record["rate_output"]
    result = dict(rate_output_id=rates["output_binding"]["dataset_id"], conditions=rates["conditions"],
                  native_basis=rates["native_normalization"], input_and_output_sources=rates["provenance"])
    if mkm:
        p = record["binding"]
        result.update(binding_sha256=p["binding_sha256"], run_id=p["run_id"], root=p["root"],
                      root_state_sha256=p["root_state_sha256"], execution=p["execution"], inputs=p["input_hashes"],
                      native_conditions=p["conditions"], dataset=p["dataset"], normalization=p["normalization"])
    else:
        w = record["window"]
        result.update(integration_sha256=record["record_sha256"], manifest_sha256=record["manifest_sha256"],
                      window_sha256=w["window_evidence_sha256"], definition=w["definition"], execution=w["result"],
                      lineage=w["checkpoint_lineage"], seed=w["seed"], native_conditions=w["conditions"],
                      dataset=w["dataset"], configuration_sha256=w["configuration_sha256"], network=w["reaction_network"],
                      sampled_spans_s=record["sampled_spans_s"], statistics=record["statistics"])
        obs = record["observations"]
        if "residence_exposure_over_desorptions" in obs:
            result["residence_exposure_over_desorptions"] = obs["residence_exposure_over_desorptions"]
        if "molecular_mapping_error" in obs:
            result["molecular_mapping"] = dict(compatibility="insufficient_evidence", reason=obs["molecular_mapping_error"])
    return result


def _provenance(dataset, supplied, scope):
    known = {ref["sha256"] for ref in dataset["source_artifacts"]}
    require(bool(known), "Missing dataset source provenance")
    require(known <= supplied, "Missing original parameter source evidence")
    for row in dataset["reactions"]:
        p = row["parameter_set"]
        require(reviewed(row["model"], dataset["network_version"], supplied)
                and row["scientifically_validated"] and p["validation"]["status"] == "accepted"
                and p["sources"] and p["energy_reference_id"]
                and p["validation"]["review"]["sha256"] in supplied
                and all(s["artifact"]["sha256"] in supplied for s in p["sources"]),
                "Missing reviewed parameter provenance for " + row["reaction_id"])
        require(scope == "synthetic_control" or row["model"].get("use_scope") != "synthetic_benchmark",
                "Synthetic benchmark requires synthetic comparison scope")


def _observed(point, kmc):
    p, w = point["binding"], kmc["window"]
    require(p["root"]["coverage"] and p["root"]["vacancy"] and p["execution"]["mat_sha256"] and
            p["execution"]["log_sha256"], "Missing MKM root evidence")
    require(w["definition"]["event_interval"] == "(start,end]" and w["definition"]["population_rule"] == "left_held"
            and w["checkpoint_lineage"] and all(k in kmc["sampled_spans_s"] for k in ("procstat", "specnum")),
            "Missing KMC event-time evidence")


def _compatible(condition, reason):
    if not condition:
        raise IncompatibleIdentity(reason)


def _check_pressures(pc, wc, rate_conditions):
    # Compare declared decimal quantities exactly. Only the derived binary64
    # V2.1 projection can round during Pa -> bar -> Pa (two operations).
    total = Decimal(str(pc["total_pressure_bar"])) * 100000
    gas = pc["partial_pressures_bar"]
    _compatible(total == Decimal(str(wc["pressure_Pa"])) and gas == wc["partial_pressure_bar"],
                "Different gas conditions or standard states")
    expected = {s: Decimal(str(v)) * 100000 for s, v in gas.items()}
    for conditions in rate_conditions:
        partials = conditions["partial_pressures"]
        observed = {p["species_id"]: p["pressure_Pa"] for p in partials}
        require(len(partials) == len(observed) and observed.keys() == expected.keys()
                and conditions["temperature_K"] == pc["temperature_K"], "Different projected gas conditions")
        pairs = [(observed[s], expected[s]) for s in expected]
        pairs.append((conditions["pressure_Pa"], total))
        for value, target in pairs:
            reference = float(target)
            require(math.isfinite(value) and abs(value - reference) <= 2 * math.ulp(reference),
                    "Different projected gas conditions")


def _common(point, kmc, left, right, *, left_root=SOURCE_ROOT):
    p, w = point["binding"], kmc["window"]
    models = [{r["reaction_id"]: r for r in d["reactions"]} for d in (left, right)]
    require_common_identities(left, right, left_root=left_root)
    pc, wc = p["conditions"], w["conditions"]
    _check_pressures(pc, wc, (point["rate_output"]["conditions"], kmc["rate_output"]["conditions"]))
    _compatible(pc["temperature_K"] == wc["temperature_K"] and pc["standard_states"] == wc["standard_states"],
                "Different gas conditions or standard states")
    for rid, row in models[0].items():
        other = models[1][rid]
        for key in ("energy_reference_id", "energy_basis", "standard_state_id"):
            _compatible(row["parameter_set"][key] == other["parameter_set"][key], f"Different {key} for {rid}")
        _compatible(sha256_json(row) == sha256_json(other), "Different parameter content, rate law or provenance for " + rid)
        param, conditions = row["parameter_set"], wc
        require(param["temperature_K"] == conditions["temperature_K"] and param["pressure_Pa"] == conditions["pressure_Pa"]
                and param["standard_states"] == w["conditions"]["standard_states"], "Parameters outside bound conditions")
        limits = param.get("validity_range") or {}
        for name in ("temperature_K", "pressure_Pa"):
            require(limits.get("min_" + name, conditions[name]) <= conditions[name] <= limits.get("max_" + name, conditions[name]),
                    "Parameter validity range exceeded")


def _assessment(ref, directory, point, kmc, left, right):
    review, digest = read_artifact(directory / ref["path"])
    require(digest == ref["sha256"] and review["format"] == "mkm-kmc-comparison-review/1", "Changed comparison review")
    require(review["mkm_binding_sha256"] == point["binding"]["binding_sha256"] and
            review["kmc_record_sha256"] == kmc["record_sha256"], "Assessment belongs to another point or window")
    require(review["reviewer"].strip() and review["target"] == "matched_stationary_ensemble"
            and review["scope"] in ("synthetic_control", "model_predictions"), "Missing matched root/window assessment")
    require(review["assessment"].strip() and review["observables"], "Missing observable-scoped ensemble assessment")
    _pinned(directory, review["ensemble_evidence"])
    for source in review["parameter_sources"]:
        _pinned(directory, source)
    supplied = {source["sha256"] for source in review["parameter_sources"]}
    for d in (left, right):
        _provenance(d, supplied, review["scope"])
    return review


def _comparison_rows(queries, point, kmc, left, right, review, decision, errors):
    rows = []
    for q in queries:
        reasons = errors.copy()
        row = dict(observable=q, compatibility=decision, reasons=reasons, mkm=None, kmc=None,
                   conversion=None, difference=None)
        for side, record, data in (("mkm", point, left), ("kmc", kmc, right)):
            if record:
                try:
                    row[side] = measure(q, record, data, mkm=side == "mkm")
                except (ValueError, KeyError, TypeError) as exc:
                    reasons.append(side + " observable: " + str(exc))
        if not reasons:
            try:
                require(q in review["observables"], "Observable absent from ensemble review")
                row["difference"], row["conversion"] = difference(q, row["mkm"], row["kmc"], review.get("mapping"),
                                                                 point["binding"], kmc["window"])
                row["compatibility"] = "comparable_after_explicit_conversion" if row["conversion"] else "comparable"
            except IncompatibleIdentity as exc:
                row["compatibility"] = "not_comparable"
                reasons.append(str(exc))
            except (ValueError, KeyError, TypeError) as exc:
                reasons.append(str(exc))
        if reasons and kmc and (issue := kmc["observations"].get("molecular_mapping_error")):
            reasons.append(issue)
        rows.append(row)
    return rows


def compare(request_path, request_sha256, *, mkm_worktree):
    """Replay both owning readers. The caller supplies a trusted request digest and MKM installation."""
    path = Path(request_path).resolve()
    request, digest = read_artifact(path)
    require(digest == request_sha256 and request["format"] == "mkm-kmc-comparison/1", "Unverified comparison request")
    require(isinstance(request["observables"], list) and request["observables"], "Missing observable requests")
    errors = []
    point = kmc = left = right = review = None
    try:
        point, left = _point(request["mkm"], path.parent, mkm_worktree)
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired) as exc:
        errors.append("MKM evidence: " + str(exc))
    try:
        kmc, right = _window(request["kmc"], path.parent)
    except (ValueError, KeyError, OSError) as exc:
        errors.append("KMC evidence: " + str(exc))
    decision = "insufficient_evidence"
    if not errors:
        try:
            _observed(point, kmc)
            _common(point, kmc, left, right, left_root=mkm_worktree or SOURCE_ROOT)
        except IncompatibleIdentity as exc:
            errors.append(str(exc))
            decision = "not_comparable"
        except (ValueError, KeyError, TypeError) as exc:
            errors.append(str(exc))
    if not errors:
        try:
            review = _assessment(request["review"], path.parent, point, kmc, left, right)
        except (KeyError, OSError, ValueError, TypeError) as exc:
            errors.append("Comparison review: " + str(exc))
    evidence = dict(mkm=_evidence(point, True), kmc=_evidence(kmc, False), request_sha256=digest,
                    requested_sources={k: request.get(k) for k in ("mkm", "kmc", "review")}, review=review)
    rows = _comparison_rows(request["observables"], point, kmc, left, right, review, decision, errors)
    result = dict(format="mkm-kmc-comparison-result/1", evidence=evidence, comparisons=rows,
                  uncertainty=dict(mkm_numerical_residuals={key: point["binding"]["root"].get(key)
                                                            for key in ("analysis_residual", "single_point_residual")}
                                   if point else None,
                                   parameter_uncertainty={side: {rid: item["uncertainty"]
                                                                for rid, item in ref["dataset"]["parameters"].items()}
                                                          for side in ("mkm", "kmc") if (ref := evidence[side])},
                                   kmc_statistics=kmc["statistics"] if kmc else None,
                                   reviewed=review.get("uncertainty") if review else None,
                                   difference_interval=None),
                  interpretation="Descriptive model comparison; no scientific acceptance or root uniqueness implied.")
    return dict(result, comparison_sha256=sha256_json(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("sha256")
    parser.add_argument("--mkm-worktree", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compare(args.request, args.sha256, mkm_worktree=args.mkm_worktree), indent=2, allow_nan=False))
