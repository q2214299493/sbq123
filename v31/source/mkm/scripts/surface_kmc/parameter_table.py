from scripts.kinetic_parameters.export_contract import per_bar, source_info, validate_export
from scripts.kinetic_parameters.laws import positive
from scripts.reaction_network.event_geometry import verify_event


def zacros(dataset):
    validate_export(dataset)
    if any("energy_prediction" in r["model"] for r in dataset["reactions"]):
        raise ValueError("MKM energy predictions have no qualified lattice-event export")
    species = {s["species_id"]: s for s in dataset["species"]}
    rows = []
    for r in dataset["reactions"]:
        event = r["model"].get("local_event")
        verify_event(event, r, species)
        p = r["parameter_set"]
        for name, rate in r["rates"].items():
            if rate is None:
                continue
            count = positive(event["patterns_per_reference_site"][name], "patterns per reference site")
            initial, final = event["initial"], event["final"]
            if name == "reverse":
                initial, final = final, initial
            converted = per_bar(rate, p["standard_states"]["gas_pressure_Pa"], count)
            rows.append({"reaction_id": r["reaction_id"], "provenance": source_info(r),
                         "direction": name, "rate_kind": "kmc_event_coefficient", "T_K": p["temperature_K"],
                         "pressure_bar": p["pressure_Pa"] / 100000, "site_ids": event["site_ids"],
                         "neighbors_zero_based": event["neighbors_zero_based"], "initial": initial, "final": final,
                         "reaction": r["direction"][name], "pre_expon": converted["coefficient"], "activ_eng_eV": 0.0,
                         "unit": converted["unit"], "gas_partial_pressure_orders": converted["gas_partial_pressure_orders"],
                         "coverage_fractions": r["model"].get("coverage_fractions", {})})
    return {"format": "zacros-event-rate-table/1", "dataset_version": dataset["dataset_version"],
            "normalization": "per matching event at listed conditions; distinct directed steps", "events": rows}
