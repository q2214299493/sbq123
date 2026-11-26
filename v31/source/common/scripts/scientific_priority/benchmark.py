"""Adapters for the published Ni/Cu synthetic pilot and the read-only Fe inventory."""

from pathlib import Path
from contextlib import closing
import sqlite3

import yaml

from scripts.artifact_io import load_json_object as read, sha256_file, sha256_json
from scripts.scientific_intake import report as intake_report

from .evidence import registry_inventory


def read_sources(root, sources):
    documents = {}
    for key, ref in sources.items():
        path = root / ref["path"]
        if sha256_file(path) != ref["sha256"]:
            raise ValueError("Evidence hash mismatch: " + key)
        documents[key] = yaml.safe_load(path.read_bytes()) if path.suffix.lower() in (".yaml", ".yml") else read(path)
    return documents


def synthetic(root):
    fixture = Path("tests/fixtures/multiphase/priority_benchmark.json")
    cfg = read(root / fixture)
    sources = dict(cfg["sources"], fixture={"path": fixture.as_posix(), "sha256": sha256_file(root / fixture)})
    d = read_sources(root, sources)
    a, parent, network = d["analysis"], d["baseline"], d["network"]
    common = d["hydrogenate"]["common"]
    if (
        a["source_hashes"] != common["baseline"]
        or a["source_hashes"]["result"] != parent["result_sha256"]
        or a["network_version"] != network["network_version"]
        or a["dataset_version"] != parent["kinetic_dataset_version"]
        or any(d[k]["baseline"]["source_hashes"] != a["source_hashes"] for k in ("intermediate", "gas"))
        or d["transfer"]["cases"]["baseline"]["source_hashes"] != a["source_hashes"]
        or not d["gas"]["complete"]
        or not d["batch"]["complete"]
        or any(d["ticket"][k] != parent[k] for k in ("question_id", "ticket_id"))
    ):
        raise ValueError("Mismatched baseline or incomplete sensitivity evidence")
    scope = dict(
        network_version=a["network_version"],
        dataset_version=a["dataset_version"],
        baseline_result_sha256=parent["result_sha256"],
        normalization=a["normalization"],
        temperature_K=a["temperature_K"],
        feed_bar=a["partial_pressures_bar"],
    )
    observable = common["observable"]
    policies = {
        k: dict(
            id=k,
            observable=observable,
            scope=scope,
            scales=cfg["scales"],
            cost_unit="core_hour",
            reliability_metric="relative_energy_rmse_eV",
            **v,
        )
        for k, v in cfg["policies"].items()
    }
    reactions = {x["definition"]["reaction_id"]: x["definition"] for x in network["reactions"]}
    species = {s["species_id"]: s for s in network["species"]}
    rates = {r["reaction_id"]: r["net_flux"] for r in a["rates"]["reactions"]}
    metrics = []
    candidates = []
    reliabilities = []
    inventory = []
    for row in cfg["candidates"]:
        key = row["id"]
        rids = row["reactions"]
        defs = [reactions[k] for k in rids]
        frame = {role: sha256_json(cfg["structures"][key + "/" + role]) for role in ("IS", "TS", "FS", "species")}
        targets = {row["state"]: frame[row["state"]]}
        c = dict(
            id=key,
            reaction_ids=rids,
            parameter=key,
            parameter_type="transition_state" if key in reactions else "intermediate",
            species_ids=sorted({s for rx in defs for k in ("reactants", "products") for s in rx[k]}),
            structures={
                k: {"id": defs[0][field], "mock_structure_sha256": frame[k]}
                for k, field in (("IS", "initial_structure_id"), ("TS", "ts_id"), ("FS", "final_structure_id"))
            },
            reaction_family=defs[0]["reaction_type"],
            phase_ids=defs[0]["phase_ids"],
            surface_ids=defs[0]["surface_ids"],
            interface_id=defs[0]["interface_id"],
            site_context=defs[0]["required_sites"] if key in reactions else species[key]["site_occupancy"],
            targets=targets,
            protocol=cfg["protocol"],
            need=row["need"],
            model_version=cfg["model"],
            error_metric="relative_energy_rmse_eV",
            scope=scope,
            absolute_net_flux=abs(rates[key]) if key in reactions else None,
            cost=dict(value=row["cost"], unit="core_hour", source="fixture"),
            parent_run_id=a["run_id"],
            ticket=d["ticket"],
            scope_label="synthetic_benchmark",
            blockers=[],
        )
        c["reaction_structures"] = {
            rid: {
                role: reactions[rid][field]
                for role, field in (("IS", "initial_structure_id"), ("TS", "ts_id"), ("FS", "final_structure_id"))
            }
            for rid in rids
        }
        if key not in reactions:
            c["structures"] = {"species": {"id": species[key]["structure_id"], "mock_structure_sha256": frame["species"]}}
        if key in reactions:
            m = d["batch"]["reactions"][key]
            direct = d["transfer"]["drc"] if key == "transfer" else d["hydrogenate"]["reactions"][key]["estimates"]["fine"]["central"]
            if m["stability"] != "stable" or m["drc"] != direct:
                raise ValueError("Unverified reaction-specific DRC")
            value = m["drc"]
            kind = "ts_drc"
            source = "batch"
        else:
            m = d["intermediate"]["pairs"]["intermediate_G-fine"]
            if m["spec"]["species_id"] != key or d["intermediate"]["step_comparison"]["intermediate_G"]["status"] != "stable":
                raise ValueError("Unverified intermediate sensitivity")
            value = m["estimates"]["central"]
            kind = "intermediate_G"
            source = "intermediate"
        metrics.append(
            dict(
                parameter=key,
                kind=kind,
                observable_kind="overall_activity",
                parameter_type=c["parameter_type"],
                scope=scope,
                observable=observable,
                coordinate="G_over_kBT",
                value=value,
                value_path=["reactions", key, "drc"] if kind == "ts_drc" else ["pairs", "intermediate_G-fine", "estimates", "central"],
                source=source,
                status="accepted",
            )
        )
        reliabilities.append(
            dict(
                model_version=c["model_version"],
                targets=targets,
                protocol=c["protocol"],
                parameter=key,
                review="accepted",
                source="fixture",
                validation_errors={"relative_energy_rmse_eV": row["validation_rmse_eV"]},
                ensemble_sd_eV=row["ensemble_sd_eV"],
                calibration=row["calibration"],
                extrapolation_grade="mock_interpolation",
                structural_distance=row["novelty"],
                distance_definition="mock descriptor distance",
                coverage=dict(
                    training_set="mock disjoint validation split",
                    composition="represented",
                    phase="represented",
                    facet="represented",
                    site="represented",
                    reaction_coordinate="partial",
                ),
            )
        )
        if row["calibration"]:
            c["information_model"] = dict(loss="squared_log_observable", expected_posterior_variance_eV2=0.0001, reference="fixture")
        candidates.append(c)
        inventory.append(
            dict(
                id="mock-verified-geometry/" + key,
                protocol=c["protocol"],
                review="accepted",
                targets=targets,
                need="minimum_geometry",
                source="fixture",
            )
        )
    gas = d["gas"]
    if gas["step_comparison"]["status"] != "stable":
        raise ValueError("Unstable feed derivative")
    context = [
        dict(
            kind="gas_order",
            source="gas",
            observable=gas["observable"],
            scope=scope,
            value=gas["pairs"]["fine"]["estimates"]["quadratic_at_zero"],
            constraint="fixed_total_proportional_remainder",
            parameter="NO-g",
        ),
        dict(
            kind="network_connectivity",
            source="analysis",
            feed_to_product=a["pathways"]["feed_to_product"],
            pathway_percentages=a["pathways"]["pathway_percentages"],
        ),
    ]
    candidates.append(dict(candidates[0], id="reuse-transfer-geometry", need="minimum_geometry"))
    return dict(
        candidates=candidates,
        metrics=metrics,
        reliability=reliabilities,
        evidence=inventory,
        sources=sources,
        inventory_source="fixture",
        context_evidence=context,
    ), policies


def fe_inventory(root, database):
    folder = root / "reports/multiphase"
    mapping = read(folder / "ch_co_registry_mapping_20261119.json")
    states = mapping["source_states"]
    ids = {k: v["structure"]["sha256"] for k, v in states.items()}
    indexed = registry_inventory(database, ids.values())
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        current = db.execute(
            "SELECT validation_status, initial_result_id, ts_result_id, final_result_id FROM ts_barriers WHERE barrier_set_id=?",
            (mapping["registry"]["barrier_set_id"],),
        ).fetchone()
    if current != ("accepted", *(states[k]["result_id"] for k in ("IS", "TS", "FS"))):
        raise ValueError("Registry barrier record differs from the reviewed Fe mapping")
    for k, s in states.items():
        if sha256_file(root / s["structure"]["path"]) != ids[k] or not any(
            h["calculation_id"] == s["calculation_id"]
            and any(r["result_id"] == s["result_id"] and r["validation_status"] == s["validation_status"] for r in h["results"])
            for h in indexed[ids[k]]
        ):
            raise ValueError("Unverified Fe structure or registered result: " + k)
    intake = intake_report([read(folder / "ch_co_intake_20261119.json")], "kinetic_handoff")
    missing = read(folder / "phase3_2_2/eligibility.json")["fe110"]["missing"][intake["reaction_id"]]
    return dict(
        format="priority-evidence-inventory/1",
        reaction_id=intake["reaction_id"],
        status="blocked",
        sources={
            f: sha256_file(folder / f)
            for f in (
                "ch_co_registry_mapping_20261119.json",
                "ch_co_intake_20261119.json",
                "phase3_2_2/eligibility.json",
                "phase2_2_chco_validation.json",
            )
        },
        registry_barrier_set=mapping["registry"]["barrier_set_id"],
        structures={k: v["structure"] for k, v in states.items()},
        registry_exact_matches=indexed,
        surface=mapping["surface_context"],
        thermal_routes=intake["thermal_routes"],
        missing=missing,
        unresolved_intake=intake["unresolved_fields"],
        scientific_importance=None,
        model_uncertainty=None,
        drc=None,
        intermediate_sensitivity=None,
        gas_order=None,
        free_energy_barriers=None,
        rate_constants=None,
        score=None,
        next_action="Review IS and FS for compatible thermal corrections or matched frequencies; confirm site inventory and kinetic parameters.",
        proposed_native_runs=0,
    )
