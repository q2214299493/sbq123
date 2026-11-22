"""Common artifact bindings and V2 envelope for explicitly requested native-result reads."""
from pathlib import Path

from scripts.artifact_io import sha256_file, sha256_json
from scripts.kinetic_data.network_binding import validate_bound_rows
from scripts.kinetic_parameters.engine import check_version
from scripts.kinetic_parameters.rate_units import convert_unit
from scripts.rate_output_v2 import generate_source_terms, validate_rate_output_v2


def require(condition, message):
    if not condition:
        raise ValueError(message)


def artifact(path, root, expected=None):
    path = Path(path).resolve()
    locator = path.relative_to(Path(root).resolve()).as_posix()
    digest = sha256_file(path)
    require(expected is None or digest == expected, f"SHA-256 differs for {path.name}")
    return {"path": locator, "sha256": digest}


def build_output(dataset, network, *, engine, run_id, conditions, basis, inputs, provenance, observations, coefficients=None):
    check_version(dataset, "dataset_version")
    check_version(network, "network_version")
    require(dataset["network_version"] == network["network_version"] and dataset["project_id"] == network["project_id"],
            "Dataset and network binding differ")
    definitions = {r["definition"]["reaction_id"]: r for r in network["reactions"]}
    rows = []
    for model in dataset["reactions"]:
        rid = model["reaction_id"]
        parameter = model["parameter_set"]["parameter_set_id"]
        entry = definitions[rid]
        require(model["direction"] == entry["direction"],
                f"Model direction differs from network for {rid}")
        rows.append(dict(reaction_id=rid, parameter_set_id=parameter, **model["direction"]["forward"], **observations[rid]))
    require(set(observations) == {r["reaction_id"] for r in rows}, "Native and modeled reaction inventories differ")
    scope = {k: dataset[k] for k in ("project_id", "network_version")}
    output = dict(format="kinetic-rate-output/2", schema_version="2.1.0", dataset_version=dataset["dataset_version"],
                  **scope, engine=engine, conditions=conditions,
                  native_normalization=dict(extent_unit="event", time_unit="s", denominator_value=1, reference_scope=scope, **basis),
                  output_binding=dict(run_id=run_id, native_inputs=inputs),
                  reaction_rates=rows, source_terms=generate_source_terms(rows), validity_range=None,
                  provenance=provenance, validation={"status": "unreviewed", "review": None})
    if coefficients is not None:
        output["rate_coefficients"] = coefficients
    output["output_binding"]["dataset_id"] = "rates-" + sha256_json(output)
    validate_rate_output_v2(output, network=network)
    validate_bound_rows(output, network, reaction_ids=[r["reaction_id"] for r in dataset["reactions"]])
    return output


def conditions_pa(temperature, total_bar, partial_bar):
    return dict(temperature_K=temperature, pressure_Pa=convert_unit(total_bar, "bar", "Pa"),
                partial_pressures=[dict(species_id=s, pressure_Pa=convert_unit(p, "bar", "Pa"))
                                   for s, p in sorted(partial_bar.items())])
