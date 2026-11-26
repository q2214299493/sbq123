"""Read-only project views of qualified records. Domain owners retain all decisions."""
from pathlib import Path

from jsonschema import ValidationError

from scripts.artifact_io import sha256_json
from scripts.kinetic_data.project_references import JSON_ROLES, manifest, resolve_sources
from scripts.kinetic_data.reaction_intake import STATES, report
from scripts.kinetic_parameters.engine import check_version
from scripts.multiphase_contracts import validate_bundle
from scripts.rate_output_v2 import validate_network_bound_rate_output
from scripts.reaction_network.builder import balance, build_network
from scripts.reaction_network.catalog import catalog, check_network_version, ownership_report

# Only these references can support the corresponding scientific claim.
REQUIRES = {
    "structures": ("network", "intake"),
    "electronic_energies": ("network", "intake"),
    "electronic_barriers": ("network",),
    "thermochemistry": ("network", "intake"),
    "kinetic_parameters": ("network", "dataset"),
    "native_rates": ("network", "rates"),
    "rate_uncertainty": ("network", "rates", "qualification", "dataset", "mkm_receipt", "result", "configuration"),
    "tof": ("network", "dataset", "configuration", "result", "mkm_receipt"),
    "stable_drc": ("network", "dataset", "configuration", "result", "mkm_receipt", "drc_plan", "drc"),
    "lattice": ("network", "observation", "graph"),
    "native_initialization": ("network", "graph", "original_manifest", "kmc_plan", "kmc_receipt", "kmc_validation"),
    "candidate_input": ("network", "graph", "candidate_manifest"),
}


def _equal(value, expected, label):
    if value != expected:
        raise ValueError(f"{label} binding differs")


def _names(value, label):
    if not isinstance(value, list) or any(not isinstance(v, str) or not v for v in value):
        raise ValueError(f"{label} must be a list of names")
    if len(value) != len(set(value)):
        raise ValueError(f"Ambiguous duplicate {label}")
    return value


def _network(source, path, digest, project, version, reaction, *, isolate=False):
    if source["format"] == "network-definition/1":
        snapshot = build_network(source, sources=[{"role": "definition", "file": path.name, "sha256": digest}])
    else:
        snapshot = source
    check_network_version(snapshot)
    _equal(snapshot["project_id"], project, "Catalyst project")
    if version:
        _equal(snapshot["network_version"], version, "Network version")
    definitions = [row["definition"] for row in snapshot["reactions"]]
    index = catalog(dict(snapshot["catalog"], species=snapshot["species"], reactions=definitions))
    ids = index["reactions"]
    if reaction is not None and reaction not in ids:
        raise ValueError("Reaction is outside the selected network")
    conservation = {}
    for definition in definitions:
        gaps = []
        result = conservation[definition["reaction_id"]] = {"unresolved": gaps}
        try:
            sites = balance(definition, index, gaps)
            if isolate:
                result["site_balance"] = sites
        except (KeyError, ValueError, TypeError) as exc:
            if not isolate:
                raise
            result["invalid"] = str(exc)
    return snapshot, {
        "version": snapshot["network_version"], "project_id": project,
        "ownership": ownership_report(snapshot), "species": [
            {k: s.get(k) for k in ("species_id", "composition", "charge", "site_occupancy", "structure_id")}
            for s in snapshot["species"]
        ], "conservation": conservation,
    }


def _scope_rows(rows, reaction_id, key):
    return {row[key]: row for row in rows if reaction_id is None or row[key] == reaction_id}


def _intake_view(name, docs, rows, digests, base):
    n = docs.get("network")
    intake = docs["intake"]
    rid = intake["reaction_id"]
    if n is not None and rid not in rows:
        raise ValueError("Intake reaction outside selected network")
    if n is not None and not any(x["role"] == "intake" and x["sha256"] == digests["intake"]
                                 for x in n["source_artifacts"]):
        raise ValueError("Intake is outside the network source bindings")
    assessment = report([intake], "thermochemistry" if name == "thermochemistry" else "electronic")
    if name == "thermochemistry":
        thermal = rows[rid]["thermochemistry"]
        if not thermal:
            return None, assessment["unresolved_fields"] or ["Missing qualified thermochemistry record"]
        values = {k: thermal.get(k) for k in ("states", "state_free_energy_ev", "reaction", "condition_values")}
        values["gibbs_ev"] = rows[rid]["energies"]["gibbs_ev"]
        return values, (
            sorted(set(thermal["issues"] + assessment["unresolved_fields"])))
    kind = "structure" if name == "structures" else "electronic_energy"
    records = {r["id"]: r for r in intake["records"]}
    values, missing = {}, []
    for state in STATES:
        field = assessment["fields"][f"{state}.{kind}"]
        record = records.get(field.get("selected"))
        if field["usable"] and record:
            values[state] = {k: record[k] for k in ("id", "value", "validation", "provenance", "acceptance")}
            values[state]["evidence_status"] = field["evidence_status"]
            origin = record["provenance"]
            ref = {"path": origin.get("source_reference"), "sha256": origin.get("source_artifact_hash")}
            local, _, _ = resolve_sources(base, [{state: ref}], None, None, None)
            values[state]["local_source"] = local[state]
            if local[state]["status"] in ("invalid_reference", "hash_mismatch"):
                missing.append(f"{state}.{kind}: {local[state]['status']}")
        else:
            missing.append(f"{state}.{kind}")
    return values, missing


def _native_rates(docs, paths, digests, reaction_id, *, include_qualification=False):
    rates = docs["rates"]
    subset = None
    if reaction_id and {row["reaction_id"] for row in rates["reaction_rates"]} == {reaction_id}:
        subset = [reaction_id]
    validate_network_bound_rate_output(rates, paths["network"], reaction_ids=subset)
    provenance = rates["provenance"]
    for role in ("dataset", "native_output"):
        if role in digests:
            _equal(provenance[role]["sha256"], digests[role], "Rate " + role)
    result = {k: rates.get(k) for k in ("conditions", "native_normalization", "engine", "validity_range",
                                          "provenance", "validation")}
    for field in ("reaction_rates", "rate_coefficients"):
        result[field] = [row for row in rates[field] if reaction_id is None or row["reaction_id"] == reaction_id]
    result["statistical_uncertainty"] = None
    if include_qualification:
        from scripts.baseline_mkm.analysis import verify_receipt

        receipt = docs["mkm_receipt"]
        inputs = {k: digests[k] for k in ("network", "dataset", "configuration")}
        verify_receipt(receipt, docs["result"], digests["result"], inputs, docs["network"],
                       docs["dataset"], docs["configuration"])
        _equal(rates["output_binding"]["run_id"], receipt["run_id"], "Rate run")
        if provenance["native_output"]["sha256"] not in receipt["output_hashes"].values():
            raise ValueError("Rate native output differs from the selected run")
        qualification = _rate_qualification(docs, digests)
        result["statistical_uncertainty"] = qualification["statistical_uncertainty"]
        result["qualification_scope"] = qualification["scope"]
    return result


def _rate_qualification(docs, digests):
    matches = [q for q in docs["qualification"].values()
               if q["receipt"]["sha256"] == digests["mkm_receipt"]
               and q["result_record"]["sha256"] == digests["result"]
               and q["configuration"]["sha256"] == digests["configuration"]]
    if len(matches) != 1:
        raise ValueError("No unique rate qualification for the selected operating point")
    return matches[0]


def _check_tof_rate_reference(ref, docs, paths, digests, reaction_id):
    if "rates" not in docs:
        raise ValueError("Custom TOF requires a verified rate output with basis_evidence")
    rates = _native_rates(docs, paths, digests, reaction_id)
    receipt = docs["mkm_receipt"]
    _equal(docs["rates"]["output_binding"]["run_id"], receipt["run_id"], "TOF rate run")
    if rates["provenance"]["native_output"]["sha256"] not in receipt["output_hashes"].values():
        raise ValueError("TOF denominator is from a different native output")
    native = rates["native_normalization"]
    for field in ("reference_id", "denominator_unit", "denominator_value", "extent_unit", "time_unit"):
        _equal(ref[field], native[field], "TOF " + field)
    _equal(ref["inventory_ids"], sorted(native["inventory_ids"]), "TOF inventories")
    _equal(ref["reference_basis"], native["basis_kind"], "TOF basis")
    if native["basis_kind"] == "other":
        _equal(native["basis_evidence"]["sha256"], ref["evidence_sha256"], "TOF basis_evidence.sha256")


def _legacy_tof_reference(docs, paths, digests, reaction_id, base):
    from scripts.artifact_io import sha256_file
    from scripts.baseline_mkm.normalization import normalization
    from scripts.runtime_resources import resource_path

    profile = _rate_qualification(docs, digests)["normalization"]
    local = (base / profile["path"]).resolve()
    if not local.is_relative_to(base.resolve()):
        raise ValueError("Rate qualification profile is outside its evidence base")
    if not local.is_file():
        local = resource_path(profile["path"])
    _equal(sha256_file(local), profile["sha256"], "Rate qualification profile")
    ref = normalization(local, docs["network"], docs["configuration"])
    _check_tof_rate_reference(ref, docs, paths, digests, reaction_id)
    return ref


def _observe(name, docs, paths, inventory, reaction_id, base):
    n = docs.get("network", {})
    digests = {k: v["actual_sha256"] for k, v in inventory.items() if v["status"] == "verified"}
    rows = {r["definition"]["reaction_id"]: r for r in n.get("reactions", [])
            if reaction_id is None or r["definition"]["reaction_id"] == reaction_id}
    if name in ("structures", "electronic_energies", "thermochemistry"):
        return _intake_view(name, docs, rows, digests, base)
    if name == "electronic_barriers":
        values = {rid: row["energies"]["electronic_ev"] for rid, row in rows.items()}
        missing = [f"{rid}.{key}" for rid, value in values.items() for key in ("forward", "reverse", "reaction")
                   if value.get(key) is None]
        return values, missing
    if name == "kinetic_parameters":
        kinetics = _scope_rows(docs["dataset"]["reactions"], reaction_id, "reaction_id")
        return {rid: row["rates"] for rid, row in kinetics.items()}, [
            message for row in kinetics.values() for message in row["missing"]]
    if name == "rate_uncertainty":
        rates = _native_rates(docs, paths, digests, reaction_id, include_qualification=True)
        uncertainty = rates["statistical_uncertainty"]
        return {"statistical_uncertainty": uncertainty, "scope": rates["qualification_scope"]}, (
            [] if uncertainty is not None else [rates["qualification_scope"]])
    if name == "native_rates":
        return _native_rates(docs, paths, digests, reaction_id), []
    if name in ("tof", "stable_drc"):
        from scripts.baseline_mkm.analysis import verify_receipt

        receipt, result = docs["mkm_receipt"], docs["result"]
        inputs = {k: digests[k] for k in ("network", "dataset", "configuration")}
        verify_receipt(receipt, result, digests["result"], inputs, n, docs["dataset"], docs["configuration"])
        if name == "tof":
            reference = result.get("normalization") or {}
            basis = reference.get("reference_basis")
            value = result["tof_s_inverse"]
            if "normalization" not in result and {"rates", "qualification"} <= digests.keys():
                from scripts.baseline_mkm.normalization import reference_rate

                reference = _legacy_tof_reference(docs, paths, digests, reaction_id, base)
                basis = reference["reference_basis"]
                value = reference_rate(value, reference)
            elif reference:
                native_basis = docs.get("rates", {}).get("native_normalization", {})
                if basis == "other" or native_basis.get("basis_kind") == "other":
                    _check_tof_rate_reference(reference, docs, paths, digests, reaction_id)
            available = basis is not None and value is not None
            missing = [] if available else ["Physical TOF needs a verified denominator and observed turnover"]
            return {"value": value if available else None, "unit": "s^-1" if available else None, "turnover_basis": basis,
                    "reference_id": reference.get("reference_id"),
                    "run_id": result["run_id"], "temperature_K": receipt["temperature_K"],
                    "partial_pressures_bar": receipt["partial_pressures_bar"]}, missing
        plan, drc = docs["drc_plan"], docs["drc"]
        _equal(drc["plan_sha256"], sha256_json(plan), "DRC plan")
        for role in (*inputs, "result"):
            _equal(plan["baseline_hashes"][role], digests[role], f"DRC {role}")
        _equal(plan["baseline_run_id"], result["run_id"], "DRC baseline run")
        ranking = [r for r in drc["ranking"] if r["reaction_id"] in rows
                   and drc["reactions"][r["reaction_id"]]["stability"] == "stable"]
        return ranking, [] if ranking else ["No stable DRC evidence for selected reactions"]
    graph = docs["graph"]
    _equal(graph["sources"]["definition"]["sha256"], digests["network"], "Graph definition")
    if name == "lattice":
        from scripts.surface_kmc.bridge_topology import analyze

        _equal(graph["sources"]["observation"]["sha256"], digests["observation"], "Graph observation")
        view = analyze(graph, docs["_definition"], docs["observation"])
        return {k: view[k] for k in ("classification", "matrix_node_order", "initial_bridges", "inventories",
                                     "inventory_reference", "boundary")}, []
    if name == "candidate_input":
        candidate = docs["candidate_manifest"]
        _equal(candidate["graph_sha256"], digests["graph"], "Candidate graph")
        members = {filename: {"path": filename, "sha256": digest} for filename, digest in candidate["files_sha256"].items()}
        file_evidence, _, _ = resolve_sources(paths["candidate_manifest"].parent, [members], None, None, None)
        unavailable = [f"{k}: {v['status']}" for k, v in file_evidence.items() if v["status"] != "verified"]
        return {"dataset_id": candidate["dataset_id"], "scope": candidate["scope"], "files": file_evidence,
                "files_sha256": candidate["files_sha256"], "native_qualified": None}, [
                    "Successful native receipt bound to this candidate is unavailable", *unavailable]
    plan, original = docs["kmc_plan"], docs["original_manifest"]
    validation, receipt = docs["kmc_validation"], docs["kmc_receipt"]
    _equal(original["graph_sha256"], digests["graph"], "Native graph")
    _equal(plan["bound_artifacts_sha256"]["native/input_manifest.json"], digests["original_manifest"], "Plan input")
    for data in (validation, receipt):
        _equal(data["plan_sha256"], digests["kmc_plan"], "Historical plan")
        _equal(data["dataset_id"], original["dataset_id"], "Native dataset")
    _equal(receipt["published_manifest_sha256"], digests["original_manifest"], "Executed input")
    return {k: validation[k] for k in ("native_initialization", "fatal", "approval_state", "scientific_acceptance")}, (
        [] if validation["native_initialization"] == "passed" else ["Native initialization did not qualify"])


def _engine(engine, requested, docs, *, include_inputs=False):
    result = {"requested": engine in requested, "execution_authorized": False, "status": "unassessed"}
    dataset = docs.get("dataset")
    if dataset is None:
        result["missing"] = ["Verified kinetic dataset and network"]
    elif not dataset["export_eligible"]:
        result.update(status="blocked", missing=sorted({gap for row in dataset["reactions"]
                     for gap in row["missing"] + (row["local_event_missing"] if engine == "kmc" else [])}))
    else:
        config = docs.get("configuration" if engine == "mkm" else "kmc_configuration")
        if config is None:
            result["missing"] = ["Verified engine configuration"]
        else:
            try:
                if engine == "mkm":
                    from scripts.baseline_mkm.single_point import qualify

                    files, manifest = qualify(docs["network"], dataset, config)
                else:
                    from scripts.native_model import assemble

                    files, manifest = assemble("zacros", dataset, config)
                result.update(status="input_eligible", missing=[])
                if include_inputs:
                    result.update(files=files, manifest=manifest)
            except DATA_ERRORS as exc:
                result.update(status="blocked", missing=[str(exc)])
                if include_inputs:
                    result["configuration_rejected"] = True
    return result


DATA_ERRORS = (ValueError, KeyError, TypeError, IndexError, AttributeError, ValidationError)


def _bind_scientific_sources(docs, paths, inventory, project_id, version, reaction, *, isolate=False):
    network_view = None
    if "network" in docs:
        try:
            source = docs.pop("network")
            n, network_view = _network(source, paths["network"], inventory["network"]["actual_sha256"],
                                       project_id, version, reaction, isolate=isolate)
            docs.update(network=n, _definition=source)
        except DATA_ERRORS as exc:
            inventory["network"].update(status="invalid_reference", reason=str(exc))
    if "dataset" in docs:
        try:
            d = docs.pop("dataset")
            check_version(d, "dataset_version")
            _equal(d["network_version"], docs["network"]["network_version"], "Kinetic network")
            _equal({r["reaction_id"] for r in d["reactions"]},
                   {r["definition"]["reaction_id"] for r in docs["network"]["reactions"]}, "Kinetic reaction IDs")
            from scripts.baseline_mkm.sensitivity_inputs import reproduce

            _equal(d, reproduce(docs["network"], d), "Reviewed kinetic dataset")
            docs["dataset"] = d
        except DATA_ERRORS as exc:
            inventory["dataset"].update(status="invalid_reference", reason=f"Kinetic dataset binding: {exc}")
    for role in ("observation", "rates", "drc_plan", "configuration", "kmc_configuration", "mkm_receipt"):
        if role in docs:
            data = docs[role]
            for field, parent, key in (("network_version", "network", "network_version"),
                                       ("network_version_id", "network", "network_version"),
                                       ("dataset_version", "dataset", "dataset_version"),
                                       ("kinetic_dataset_version", "dataset", "dataset_version")):
                if field in data and parent in docs and data[field] != docs[parent][key]:
                    inventory[role].update(status="invalid_reference", reason=f"{field} mismatch")
                    del docs[role]
                    break
    return network_view


def _catalog_view(docs, inventory, project_id, network_view):
    if "catalog" not in docs:
        return network_view["ownership"] if network_view else None
    try:
        source = docs["catalog"]
        if "schema_version" in source:
            validate_bundle(source)
        records = catalog(source)
        _equal(list(records["projects"]), [project_id], "Catalog project")
        view = ownership_report(source)
        if network_view:
            for group in ("surfaces", "phases", "sites", "interfaces"):
                _equal(view[group], network_view["ownership"][group], "Catalog " + group)
        return view
    except DATA_ERRORS as exc:
        inventory["catalog"].update(status="invalid_reference", reason=str(exc))
        return None


def _inspect_context(project, task, context, base, kinetic_readiness):
    project_id = project.get("catalyst_project_id", project["project_id"])
    version = context.get("network_version", task.get("network_version"))
    reaction = context.get("reaction_id", task.get("reaction_id"))
    sources = [project.get("sources", {}), task.get("sources", {})]
    if context is not task:
        sources.append(context.get("sources", {}))
    inventory, docs, paths = resolve_sources(base, sources, project_id, version, reaction)
    network_view = _bind_scientific_sources(docs, paths, inventory, project_id, version, reaction, isolate=kinetic_readiness)
    catalyst = _catalog_view(docs, inventory, project_id, network_view)
    names = _names(context.get("requested_observables", task.get("requested_observables", [])), "observables")
    engines = _names(context.get("engine_routes", task.get("engine_routes", [])), "engine routes")
    if set(engines) - {"mkm", "kmc"}:
        raise ValueError("Unknown requested engine route")
    if kinetic_readiness:
        defaults = ("native_rates", "tof", "stable_drc", "lattice", "native_initialization", "candidate_input")
        names = names + [name for name in defaults if name not in names and all(k in inventory for k in REQUIRES[name])]
    observables = _observables(names, docs, paths, inventory, reaction, base)
    pipeline = {}
    if kinetic_readiness:
        rows, eligible = _kinetic_pipeline(docs, inventory, network_view, observables, reaction, engines, base,
                                         context.get("thermal_phase", task.get("thermal_phase")))
        pipeline["kinetic_readiness"] = rows
    else:
        eligible = {e: _engine(e, engines, docs) for e in ("mkm", "kmc")}
    historical = observables.get("native_initialization", {})
    if historical.get("value", {}) and historical["value"]["native_initialization"] == "failed":
        eligible["kmc"].update(status="blocked", historical_initialization="failed")
    conditions = _operating_conditions(docs, observables)
    return {"reaction_id": reaction, "operating_point_id": context.get("operating_point_id", task.get("operating_point_id")),
            "operating_conditions": conditions,
            "network": network_view, "catalyst_ownership": catalyst, "evidence": inventory, "observables": observables,
            "engines": eligible, **pipeline}


def _observables(names, docs, paths, inventory, reaction, base):
    observables = {}
    for name in names:
        roles = REQUIRES.get(name, ())
        if name in ("structures", "electronic_energies") and "network" not in inventory:
            roles = ("intake",)
        if name == "native_rates":
            roles += tuple(k for k in ("dataset", "native_output") if k in inventory)

        missing = [k for k in roles if k not in (docs if k in JSON_ROLES else paths)]
        value = None
        if not roles:
            status, gaps = "unsupported_observable", ["No existing inspection for this observable"]
        elif missing:
            gaps = [f"{k}: {inventory.get(k, {}).get('status', 'missing_scientific_evidence')}" for k in missing]
            status = "missing_scientific_evidence" if all(k not in inventory for k in missing) else "unavailable"
        else:
            try:
                value, gaps = _observe(name, docs, paths, inventory, reaction, base)
                status = "scientifically_blocked" if gaps else "available"
                if any(g.endswith((": hash_mismatch", ": invalid_reference")) for g in gaps):
                    status = "invalid_reference"
            except DATA_ERRORS as exc:
                status, gaps = "invalid_reference", [str(exc)]
        observables[name] = {"status": status, "sources": list(roles), "value": value, "missing": gaps,
                             "blocker": gaps[0] if gaps else None}
    return observables


def _operating_conditions(docs, observables):
    conditions = {}
    if ("configuration" in docs and "dataset" in docs
            and docs["configuration"].get("dataset_version") == docs["dataset"]["dataset_version"]):
        conditions["configuration"] = {k: docs["configuration"][k] for k in
                                       ("temperature_K", "total_pressure_bar", "partial_pressure_bar")
                                       if k in docs["configuration"]}
    if observables.get("native_rates", {}).get("status") == "available":
        conditions["rates"] = observables["native_rates"]["value"]["conditions"]
    if "dataset" in docs:
        conditions["parameters"] = {r["reaction_id"]: {k: r["parameter_set"].get(k) for k in
                                    ("temperature_K", "pressure_Pa", "standard_state_id")}
                                    for r in docs["dataset"]["reactions"] if r.get("parameter_set")}
    return conditions


def inspect_project(project_path, task_path, *, kinetic_readiness=False):
    project_path, task_path = Path(project_path), Path(task_path)
    project, task = manifest(project_path), manifest(task_path)
    if type(project.get("version")) is not int or project["version"] != 1:
        raise ValueError("Unsupported research project version")
    if "version" in task and (type(task["version"]) is not int or task["version"] != 1):
        raise ValueError("Unsupported research task version")
    for obj, field in ((project, "project_id"), (task, "task_id")):
        if not isinstance(obj.get(field), str) or not obj[field].strip():
            raise ValueError(f"Missing {field}")
    if task.get("project_id", project["project_id"]) != project["project_id"]:
        raise ValueError("Task belongs to a different research project")
    base = project.get("evidence_base")
    if base is not None and (not isinstance(base, str) or not base.strip()):
        raise ValueError("Invalid evidence_base")
    base_path = (project_path.parent / base).resolve() if base is not None else None
    contexts = task.get("contexts", [task])
    if not isinstance(contexts, list) or not contexts or not all(isinstance(c, dict) for c in contexts):
        raise ValueError("Expected one or more task contexts")
    keys = [(c.get("reaction_id", task.get("reaction_id")), c.get("operating_point_id", task.get("operating_point_id")))
            for c in contexts]
    if any(x is not None and not isinstance(x, str) for pair in keys for x in pair) or len(keys) != len(set(keys)):
        raise ValueError("Invalid or ambiguous reaction/operating-point scope")
    inspected = [_inspect_context(project, task, c, base_path, kinetic_readiness) for c in contexts]
    return {"project_id": project["project_id"], "objective": project.get("objective"),
            "system": project.get("system"), "catalyst_project_id": project.get("catalyst_project_id", project["project_id"]),
            "task_id": task["task_id"], "evidence_base": base, "execution_authorized": False,
            "constraints": {k: task[k] for k in ("authorized_scope", "forbidden") if k in task},
            "contexts": inspected}


def _pipeline_bindings(docs):
    if "models" in docs:
        return docs["models"]
    if "dataset" in docs:
        dataset = docs["dataset"]
        return {"network_version": dataset["network_version"],
                "models": [r["model"] for r in dataset["reactions"] if r["model"] is not None]}
    return None


def _pipeline_errors(docs, inventory, network, reaction, base):
    ids = {row["definition"]["reaction_id"] for row in network["reactions"]}
    errors = {rid: {} for rid in ids}
    for role in ("dataset", "models", "intake", "ts_review", "catalog"):
        ref = inventory.get(role)
        if ref and ref["status"] != "verified":
            target = reaction or (docs.get("intake", {}).get("reaction_id") if role in ("intake", "ts_review") else None)
            for rid in ids if target is None or role in ("dataset", "models", "catalog") else [target]:
                errors[rid][role] = f"{role}: {ref['status']}"
    intake = docs.get("intake")
    if intake:
        rid = intake["reaction_id"]
        if rid not in ids:
            raise ValueError("Intake reaction outside the selected network")
        try:
            selected = {f.get("selected") for f in report([intake], "thermochemistry")["fields"].values() if f["usable"]}
            refs = {rec["id"]: {"path": rec["provenance"]["source_reference"],
                                "sha256": rec["provenance"]["source_artifact_hash"]}
                    for rec in intake["records"] if rec["id"] in selected and rec["provenance"].get("source_artifact_hash")}
            # Record IDs are arbitrary. Resolve each as opaque bytes, even if its ID is also a document role.
            local, _, _ = resolve_sources(base, [{"record/" + k: v for k, v in refs.items()}], None, None, None)
            damaged = [f"{k}: {v['status']}" for k, v in local.items()
                       if v["status"] in ("invalid_reference", "hash_mismatch")]
            if damaged:
                errors[rid]["intake"] = ", ".join(damaged)
        except DATA_ERRORS as exc:
            errors[rid]["intake"] = str(exc)
    return errors


def _reaction_engine(engine, row, assembled, species, outputs):
    kinetic = row["kinetics"]
    issues = list(row["missing"])
    if engine == "kmc" and kinetic:
        from scripts.kinetic_parameters.export import verify_event

        try:
            verify_event(kinetic["local_event"], {"site_balance": row["conservation"]["site_balance"],
                                                "direction": row["direction"]}, species)
        except DATA_ERRORS as exc:
            issues.append(str(exc))
    if issues or row["status"] != "qualified":
        status = "blocked"
    elif assembled.get("configuration_rejected"):
        status = "blocked"
    elif assembled["status"] == "input_eligible":
        status = "input_eligible"
    else:
        status = "parameters_qualified"
    return {"status": status, "network_input_status": assembled["status"],
            "missing": issues or assembled.get("missing", []), "usable_outputs": outputs}


def _qualify_rows(docs, inventory, view, reaction, base, phase):
    from scripts.kinetic_parameters.engine import qualify_network_rows

    network = docs.get("network")
    rows, dataset, problems = {}, None, []
    if network:
        try:
            errors = _pipeline_errors(docs, inventory, network, reaction, base)
            rows, dataset = qualify_network_rows(
                network, _pipeline_bindings(docs), conservation=view["conservation"], intake=docs.get("intake"),
                review=docs.get("ts_review"), phase=phase, input_errors=errors,
                intake_bound=any(a["role"] == "intake" and a["sha256"] == inventory.get("intake", {}).get("actual_sha256")
                                 for a in network["source_artifacts"]),
                verified_hashes=[v["actual_sha256"] for v in inventory.values() if v["status"] == "verified"])
            if "models" in docs and "dataset" in docs:
                archived = {r["reaction_id"]: r["model"] for r in docs["dataset"]["reactions"]}
                supplied = {r["reaction_id"]: r for r in docs["models"]["models"]}
                for rid, row in rows.items():
                    if archived[rid] != supplied.get(rid):
                        row.update(status="invalid_input", kinetics=None)
                        row["missing"].append("Selected model differs from archived kinetic dataset")
                        dataset = None
            if dataset and "dataset" in docs:
                _equal(dataset, docs["dataset"], "Regenerated kinetic dataset")
        except DATA_ERRORS as exc:
            dataset = None
            problems.append(str(exc))
            for row in rows.values():
                row.update(status="invalid_input", kinetics=None)
                row["missing"].append(str(exc))
    else:
        problems.append(inventory.get("network", {}).get("reason", "Missing verified reaction network"))
    return rows, dataset, problems


def _kinetic_pipeline(docs, inventory, view, observables, reaction, engines, base, phase):
    network = docs.get("network")
    rows, dataset, problems = _qualify_rows(docs, inventory, view, reaction, base, phase)
    working = dict(docs, dataset=dataset)
    if dataset and dataset["export_eligible"] and any(row["status"] != "qualified" for row in rows.values()):
        working["dataset"] = None
    eligible = {e: _engine(e, engines, working, include_inputs=True) for e in ("mkm", "kmc")}
    for result in eligible.values():
        if result["status"] != "input_eligible":
            result["status"] = "blocked"
            if rows and not dataset:
                result["missing"] = ["Complete network-bound kinetic dataset required for input assembly"]
            result["missing"] = list(dict.fromkeys(problems + [
                reason for row in rows.values() for reason in row["missing"]] + result.get("missing", [])))
    usable = [name for name, result in observables.items() if result["status"] == "available"]
    mkm = eligible["mkm"]
    if "tof" in usable and "manifest" in mkm:
        bound = mkm["manifest"]["files"] == docs["mkm_receipt"].get("native_input_hashes")
        mkm["archived_input_hashes_match"] = bound
        if not bound:
            usable = [name for name in usable if name not in ("tof", "stable_drc", "native_rates")]
            problems.append("Reconstructed input bytes differ from the archived MKM run")
    if "tof" in usable and not mkm.get("archived_input_hashes_match"):
        usable = [name for name in usable if name not in ("tof", "stable_drc")]
    species = {r["species_id"]: r for r in (network or {}).get("species", [])}
    native = observables.get("native_rates", {})
    stable_drc = {r["reaction_id"] for r in observables["stable_drc"]["value"]} if "stable_drc" in usable else set()
    for rid, row in rows.items():
        row["evidence_roles"] = [k for k in ("network", "models", "dataset") if k in inventory]
        if docs.get("intake", {}).get("reaction_id") == rid:
            row["evidence_roles"].extend(k for k in ("intake", "ts_review") if k in inventory)
        row["engines"] = {
            e: _reaction_engine(e, row, result, species,
                                [k for k in usable if k in (("tof", "stable_drc") if e == "mkm" else ("lattice",))
                                 and (k != "stable_drc" or rid in stable_drc)])
            for e, result in eligible.items()
        }
        row["native_normalization"] = None
        if "native_rates" in usable and any(r["reaction_id"] == rid for r in native["value"]["reaction_rates"]):
            row["native_normalization"] = native["value"]["native_normalization"]
            row["native_coefficients"] = [r for r in native["value"]["rate_coefficients"] if r["reaction_id"] == rid]
    selected = {k: v for k, v in rows.items() if reaction is None or k == reaction}
    return {"reactions": selected, "issues": problems, "usable_outputs": usable,
            "dataset_version": (dataset or {}).get("dataset_version"), "execution_authorized": False}, eligible
