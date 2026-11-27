"""Prepare independently approved CATKINAS single points on a temperature/feed grid and replay them offline."""
import argparse
from itertools import product
import json
from math import fsum, isclose
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from scripts.artifact_io import require_sha256, sha256_bytes, sha256_file, sha256_json, write_json_exclusive as save
from scripts.baseline_mkm import single_point as point
from scripts.baseline_mkm.steady_states import observe
from scripts.multiphase_contracts import decode_unique_json, read_unique_json as read
from scripts.reaction_network.builder import artifact_hashes
from scripts.reaction_network.thermodynamics import thermal_evidence
from scripts.runtime_resources import resource_path
from scripts.scientific_validation import validate_finite_tree

DATA_ERRORS = (ValueError, KeyError, TypeError, IndexError, OSError, ValidationError)


def axes(spec):
    schema = read(resource_path("configs/kinetics/catkinas_condition_grid.schema.json"))
    error = next(Draft202012Validator(schema).iter_errors(spec), None)
    if error:
        raise ValueError(f"{error.json_path}: {error.message}")
    validate_finite_tree(spec)
    temps, feeds, gas = spec["temperatures_K"], spec["feeds_bar"], spec["pressure_species_id"]
    if any(gas not in f or f.keys() != feeds[0].keys() or fsum(f.values()) <= 0 for f in feeds):
        raise ValueError("Every feed must name the pressure axis and the same complete positive-total gas inventory")
    if len({f[gas] for f in feeds}) != len(feeds) or len(temps) * len(feeds) < 2:
        raise ValueError("A scan requires distinct coordinates and at least two points")
    return temps, feeds


def source(base, record):
    path = (base / record["path"]).resolve()
    raw = path.read_bytes()
    if sha256_bytes(raw) != record["sha256"]:
        raise ValueError(f"Source SHA-256 differs: {path.name}")
    return path, raw


def electronic_method(models, electronic, verified, identity):
    """A signed synthetic Hamiltonian or a reviewed project method linked to these electronic sources."""
    if identity is None:
        for m, sources in models:
            synthetic = {s["sha256"] for s in m["sources"] if s["kind"] == "synthetic"}
            if m.get("use_scope") != "synthetic_benchmark" or not sources <= synthetic:
                raise ValueError("Missing reviewed electronic method and convention identity")
        return "reviewed_synthetic"
    digest, record = identity
    keys = {"format", "electronic_sources", "dft_method_sha256", "electronic_conventions_sha256"}
    if (not isinstance(record, dict) or record.keys() != keys or record["format"] != "catkinas-electronic-identity/1"
            or digest not in verified or not isinstance(record["electronic_sources"], list)
            or set(record["electronic_sources"]) != electronic
            or any(digest not in {s["sha256"] for s in m["sources"]} for m, _ in models)):
        raise ValueError("Electronic identity is not bound to these reviewed models and electronic sources")
    method = {}
    for key in ("dft_method_sha256", "electronic_conventions_sha256"):
        method[key] = require_sha256(record[key], label=key)
        if method[key] not in verified:
            raise ValueError(f"Missing verified {key} anchor")
    return method


def family(n, d, c, identity=None):
    sources = n["source_artifacts"]
    verified = {s["sha256"] for s in sources if s["role"] == "verified_evidence"}
    catalog = n["catalog"]
    for structure in [*catalog["phases"], *catalog["surfaces"], *catalog["interfaces"], *n["species"]]:
        if not structure.get("structure_id") or (structure.get("structural_provenance") or {}).get("sha256") not in verified:
            raise ValueError("Missing verified structure identity")

    definitions, electronic_by_reaction, variable = {}, {}, set()
    for row in n["reactions"]:
        r = row["definition"]
        rid = r["reaction_id"]
        fixed = {k: v for k, v in r.items() if k not in ("free_energies", "validation", "eligibility", "provenance")}
        fixed["provenance"] = [s for s in r["provenance"] if s["kind"] != "thermal_correction"]
        if thermal_evidence(r, row.get("thermochemistry")) != row["energies"]:
            raise ValueError(f"Energy evidence differs from the network for {rid}")
        thermal = row.get("thermochemistry") or {}
        fixed["electronic_sources"] = thermal.get("electronic_sources")
        fixed["thermal_basis"] = row["energies"]["thermal_basis"]
        fixed["standard_state"] = row["energies"]["standard_state"]
        electronic = set(artifact_hashes([r.get("electronic_energies"), fixed["electronic_sources"]]))
        if not electronic or not electronic <= verified:
            raise ValueError(f"Missing verified electronic source identity for {rid}")
        electronic_by_reaction[rid] = electronic
        definitions[rid] = fixed
        gibbs = set(artifact_hashes(r.get("free_energies")))
        gibbs.update(artifact_hashes(thermal.get("states")))
        if not gibbs or not gibbs <= verified:
            raise ValueError(f"Missing bound Gibbs evidence for {rid}")
        variable.update(gibbs)
    laws = {}
    models = []
    for row in d["reactions"]:
        m, p = row["model"], row["parameter_set"]
        models.append((m, electronic_by_reaction[row["reaction_id"]]))
        parameter_sources = [src for src in p["sources"] if src["kind"] != "electronic_structure"]
        variable.update(artifact_hashes([parameter_sources, p["validation"]]))
        model = {k: v for k, v in m.items() if k not in ("parameter_set_id", "parameter_input", "scientific_review", "sources")}
        for side in ("forward", "reverse"):
            model[side] = {k: v for k, v in m[side].items() if k not in ("kappa", "sticking")}
        laws[row["reaction_id"]] = {
            "model": model,
            "electronic_parameter_sources": [src for src in p["sources"] if src["kind"] == "electronic_structure"],
            "parameter": {k: p[k] for k in ("energy_basis", "energy_reference_id", "standard_state_id", "standard_states",
                                            "rate_law_id", "degeneracy", "coverage_terms")},
            "prefactors": [None if p[side] is None else
                           {k: v for k, v in p[side].items() if k not in ("activation_energy", "prefactor")}
                           for side in ("forward", "reverse")],
        }
    config = {k: v for k, v in c.items() if k not in ("dataset_version", "temperature_K", "total_pressure_bar", "partial_pressure_bar")}
    method = electronic_method(models, set.union(*electronic_by_reaction.values()), verified, identity)
    if identity is not None:
        variable.add(identity[0])  # Compare the reviewed method and conventions, independent of envelope encoding.
    represented = variable | set(artifact_hashes([catalog, n["species"], definitions, laws]))
    # Mixed definition/review files are already bound by network_version and projected above.
    # Unknown source roles remain invariant, even when their bytes also supply point parameters.
    stable_sources = sorted((s["role"], s["sha256"]) for s in sources
                            if s["role"] not in ("definition", "thermochemistry", "network_review")
                            and not (s["role"] == "verified_evidence" and s["sha256"] in represented))
    projected = {"network_version", "catalog", "species", "reactions", "parameter_sets", "source_artifacts",
                 "definition_sha256", "thermochemistry_version", "acceptance_record", "validation_report"}
    network_identity = {k: v for k, v in n.items() if k not in projected}
    return sha256_json(dict(network=network_identity, catalog=catalog, species=n["species"], method=method,
                            sources=stable_sources, reactions=definitions, laws=laws, config=config))


def model_inputs(base, root, entry):
    paths, docs = {}, {}
    keys = ["network", "dataset", "configuration"]
    if "electronic_identity" in entry:
        keys.append("electronic_identity")
    for key in keys:
        record = entry[key]
        snapshot = root / (require_sha256(record["sha256"], label=key) + ".json")
        if base is None:  # Offline collection uses only the immutable scan snapshots.
            _, raw = source(root, dict(record, path=snapshot.name))
        else:
            _, raw = source(base, record)
            if not snapshot.exists():
                with snapshot.open("xb") as out:
                    out.write(raw)
        docs[key] = decode_unique_json(raw)
        paths[key] = snapshot
    return docs, paths


def qualify_model(entry, docs, paths):
    n, d, c = (docs[k] for k in ("network", "dataset", "configuration"))
    if any(k in d for k in ("sensitivity_perturbation", "ts_perturbation")):
        raise ValueError("Perturbation datasets belong to their bounded executors")
    point.qualify(n, d, c)
    for r in d["reactions"]:
        p = r["parameter_set"]
        if p["temperature_K"] != entry["temperature_K"] or r["energies"]["temperature_k"] != p["temperature_K"]:
            raise ValueError("No Gibbs and kinetic evidence at requested temperature")
        if not isclose(p["pressure_Pa"] / 1e5, entry["total_pressure_bar"], rel_tol=1e-12, abs_tol=0):
            raise ValueError("Reviewed parameter pressure differs from declared total")
        if r["equilibrium"]["log_ratio_residual"] is None:
            raise ValueError("Missing directional detailed-balance check")
    identity = (entry["electronic_identity"]["sha256"], docs["electronic_identity"]) if "electronic_identity" in docs else None
    return dict(paths=paths, config=c, family=family(n, d, c, identity),
                pressure_ranges=[r["parameter_set"]["validity_range"] for r in d["reactions"]])


def prepare_point(root, row, entry, model, tickets, ticket_id, matlab):
    total_pa = fsum(row["partial_pressure_bar"].values()) * 1e5
    if any(not r["min_pressure_Pa"] <= total_pa <= r["max_pressure_Pa"] for r in model["pressure_ranges"]):
        raise ValueError("Requested feed total outside parameter validity range")
    cfg = dict(model["config"], partial_pressure_bar=row["partial_pressure_bar"])
    cfg_path = save(root / (row["run"] + ".json"), cfg)
    view = point.prepare(root / row["run"], model["paths"]["network"], model["paths"]["dataset"], cfg_path,
                         tickets, ticket_id, matlab, normalization_path=model["profile"])
    if view["stage"] != "AWAITING_APPROVAL":
        raise ValueError(str(view.get("missing_data", view["stage"])))
    plan = read(root / row["run"] / "plan.json")
    if (plan["normalization_profile_sha256"] != (entry.get("normalization") or {}).get("sha256")
            or plan["input_hashes"]["network"] != entry["network"]["sha256"]
            or plan["input_hashes"]["dataset"] != entry["dataset"]["sha256"]):
        raise ValueError("Prepared plan differs from scan evidence")
    return sha256_json(plan)


def scan_models(base, root, entries):
    models, errors = [], []
    reference_family = None
    for index, entry in enumerate(entries):
        try:
            docs, paths = model_inputs(base, root, entry)
            model = qualify_model(entry, docs, paths)
            signature = model["family"]
            if index == 0:
                reference_family = signature
            if signature != reference_family:
                raise ValueError("Model family differs or the designated reference identity is unavailable")
            if base is not None:
                model["profile"] = source(base, entry["normalization"])[0] if entry.get("normalization") else None
            models.append(model)
            errors.append(None)
        except DATA_ERRORS as exc:
            models.append(None)
            errors.append(str(exc))
    return models, errors


def prepare(root, request, tickets, ticket_id, matlab):
    raw = request.read_bytes()
    spec = decode_unique_json(raw)
    temps, feeds = axes(spec)
    root.mkdir(parents=True, exist_ok=False)
    models, errors = scan_models(request.parent, root, spec["models"])
    rows = []
    for i, (t, feed) in enumerate(product(temps, feeds)):
        row = dict(run=f"point-{i+1:04d}", temperature_K=t, partial_pressure_bar=feed, model=None, plan_sha256=None, reason=None)
        matches = [j for j, e in enumerate(spec["models"]) if e["temperature_K"] == t
                   and isclose(e["total_pressure_bar"], fsum(feed.values()), rel_tol=1e-12, abs_tol=0)]
        try:
            if len(matches) != 1:
                raise ValueError("No unique reviewed model for this temperature and total pressure")
            j, = matches
            row["model"] = j
            if errors[j]:
                raise ValueError(errors[j])
            row["plan_sha256"] = prepare_point(root, row, spec["models"][j], models[j], tickets, ticket_id, matlab)
        except DATA_ERRORS as exc:
            row["reason"] = str(exc)
        rows.append(row)
    manifest = save(root / "grid.json", dict(format="catkinas-condition-plan/1", request_sha256=sha256_bytes(raw),
                    pressure_species_id=spec["pressure_species_id"], temperatures_K=temps, feeds_bar=feeds,
                    models=spec["models"], model_errors=errors, points=rows))
    return dict(manifest=str(manifest.resolve()), sha256=sha256_file(manifest))


def collect_point(root, planned):
    row = dict(planned, status="UNQUALIFIED", convergence="unknown", result=None)
    if row["reason"] is not None:
        return row
    run = root / row["run"]
    try:
        plan = read(run / "plan.json")
        if sha256_json(plan) != row["plan_sha256"] or plan["temperature_K"] != row["temperature_K"] or plan["partial_pressures_bar"] != row["partial_pressure_bar"]:
            raise ValueError("Changed plan or coordinate binding")
        state = point.status(run)
        row.update(status=state["stage"], convergence=state["convergence"])
        if state["stage"] != "ACCEPTED":
            row["reason"] = str(state.get("missing_data") or state.get("reason") or state.get("failure_stage") or state["stage"])
            return row
        result = observe(run)
        if result["plan_sha256"] != row["plan_sha256"]:
            raise ValueError("Replayed plan differs from scan")
        raw = (run / "result.json").read_bytes()
        if sha256_bytes(raw) != result["result_sha256"]:
            raise ValueError("Replayed result changed")
        measured = decode_unique_json(raw)
        dataset = (run / "dataset.json").read_bytes()
        if sha256_bytes(dataset) != result["dataset_sha256"]:
            raise ValueError("Reviewed kinetic evidence changed")
        applicability = {r["reaction_id"]: dict(gibbs_temperature_K=r["energies"]["temperature_k"],
                         validity_range=r["parameter_set"]["validity_range"], equilibrium=r["equilibrium"])
                         for r in decode_unique_json(dataset)["reactions"]}
        result.update(reactions=measured["reactions"], molar_selectivity=measured["molar_selectivity"], kinetic_applicability=applicability,
                      tof_qualification="qualified" if result["tof"]["per_reference_s"] is not None else "unavailable",
                      network_version=plan["network_version_id"], dataset_version=plan["kinetic_dataset_version"],
                      quality=measured["quality"], native_outputs=state["output_hashes"], solver_settings=plan["solver_settings"])
        row.update(status="QUALIFIED", result=result)
    except DATA_ERRORS as exc:
        row.update(status="INVALID_EVIDENCE", convergence="unverified", reason=str(exc))
    return row


def difference(a, b):
    if a is None or b is None or a.keys() != b.keys():
        return None
    return {k: b[k] - a[k] if a[k] is not None and b[k] is not None else None for k in a}


def deltas(a, b):
    if a is None or b is None or a["runtime"] != b["runtime"]:
        return None
    refs = [{k: v for k, v in (r["normalization"] or {}).items() if k != "network_version"} for r in (a, b)]
    physical = bool(refs[0]) and refs[0] == refs[1]
    native = not any(refs) and (a["network_sha256"], a["dataset_sha256"]) == (b["network_sha256"], b["dataset_sha256"])
    left, right = (r["tof"]["per_reference_s"] for r in (a, b))
    return dict(coverage=difference(a["coverage"], b["coverage"]), molar_selectivity=difference(a["molar_selectivity"], b["molar_selectivity"]),
                net_rate=difference(a["net_rate"], b["net_rate"]) if (physical or native) and a["net_rate_unit"] == b["net_rate_unit"] else None,
                tof=right-left if physical and left is not None and right is not None else None)


def collect(path, expected_sha256):
    raw = path.read_bytes()
    if sha256_bytes(raw) != expected_sha256:
        raise ValueError("Grid manifest SHA-256 differs")
    plan = decode_unique_json(raw)
    if plan["format"] != "catkinas-condition-plan/1":
        raise ValueError("Unsupported grid manifest")
    _, identity_errors = scan_models(None, path.parent, plan["models"])
    rows = []
    for i, ((t, feed), planned) in enumerate(zip(product(plan["temperatures_K"], plan["feeds_bar"]), plan["points"], strict=True)):
        if (planned["run"], planned["temperature_K"], planned["partial_pressure_bar"]) != (f"point-{i+1:04d}", t, feed):
            raise ValueError("Invalid grid member or coordinates")
        if planned["reason"] is None and identity_errors[planned["model"]]:
            planned = dict(planned, reason=identity_errors[planned["model"]])
        rows.append(collect_point(path.parent, planned))
    comparisons = []
    width = len(plan["feeds_bar"])
    for i, row in enumerate(rows):
        for axis, previous in (("temperature_K", i-width), ("partial_pressure_bar", i-1 if i % width else -1)):
            if previous >= 0:
                start = rows[previous]
                comparisons.append(dict(axis=axis, start=start["run"], end=row["run"], delta=deltas(start["result"], row["result"])))
    return dict(format="catkinas-condition-result/1", manifest_sha256=expected_sha256, pressure_species_id=plan["pressure_species_id"],
                models=plan["models"], points=rows, comparisons=comparisons)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    for k in ("root", "request", "tickets"):
        prep.add_argument(k, type=Path)
    prep.add_argument("ticket_id")
    prep.add_argument("matlab", type=Path)
    report = commands.add_parser("collect")
    report.add_argument("path", type=Path)
    report.add_argument("expected_sha256")
    report.add_argument("output", type=Path)
    args = vars(parser.parse_args())
    if args.pop("command") == "prepare":
        print(json.dumps(prepare(**args), allow_nan=False, indent=2))
    else:
        output = args.pop("output")
        save(output, collect(**args))


if __name__ == "__main__":
    main()
