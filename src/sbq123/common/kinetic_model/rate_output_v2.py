"""Read-only V2 reaction progress and stoichiometric source terms on one native basis."""
from __future__ import annotations

import argparse
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from sbq123.common.artifacts.artifact_io import sha256_bytes, sha256_file, sha256_json
from sbq123.common.evidence.kinetic_data.network_binding import validate_bound_rows
from sbq123.common.evidence.kinetic_data.stoichiometric_sources import finite_sum as _sum
from sbq123.common.evidence.kinetic_data.stoichiometric_sources import generate_source_terms as generate_source_terms
from sbq123.common.evidence.kinetic_data.stoichiometric_sources import indexed as _index
from sbq123.common.evidence.kinetic_data.stoichiometric_sources import rate_matches as _matches
from sbq123.common.evidence.kinetic_data.stoichiometric_sources import source_residuals
from sbq123.common.artifacts.artifact_io import check_version
from sbq123.common.kinetic_model.kinetic_parameters.rate_normalization import basis_identity as basis_identity
from sbq123.common.kinetic_model.kinetic_parameters.rate_normalization import convert_checked_rate, denominator_scale
from sbq123.common.kinetic_model.kinetic_parameters.rate_units import convert_coefficient
from sbq123.common.workflow.multiphase_contracts import _check_finite, decode_unique_json, read_unique_json
from sbq123.common.workflow.runtime_resources import resource_path


@lru_cache(maxsize=2)
def _validator(version="2.0.0"):
    names = ("kinetics/rate_output_v2", "kinetics/rate_source_terms_v2", "catalysis/common",
             "kinetics/reaction", "kinetics/kinetic_parameter", "kinetics/simulation_run")
    if version == "2.1.0":
        names = ("kinetics/rate_output_v2_1", *names)
    schemas = [read_unique_json(resource_path(f"configs/{name}.schema.json")) for name in names]
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    )
    return Draft202012Validator(schemas[0], registry=registry)


def _check_progress(row):
    # An excluded direction has no contribution. An unobserved direction has no known value.
    forward, reverse = (row[key] for key in ("forward", "reverse"))
    if forward == reverse == "not_applicable":
        raise ValueError("At least one reaction direction must be applicable")
    forward = 0 if forward == "not_applicable" else forward
    reverse = 0 if reverse == "not_applicable" else reverse
    net = row["net"]
    if forward is not None and reverse is not None:
        if net is None or not _matches(net, forward - reverse):
            raise ValueError(f"{row['reaction_id']}: net must equal forward minus reverse")
    elif net is not None:
        if "net_evidence" not in row:
            raise ValueError("A known net with unavailable directional flux requires independent net_evidence")
        if forward is not None and net > forward and not _matches(net, forward):
            raise ValueError("Independent net exceeds the known forward flux")
        if reverse is not None and net < -reverse and not _matches(net, -reverse):
            raise ValueError("Independent net contradicts the known reverse flux")
    if net is None and "net_evidence" in row:
        raise ValueError("net_evidence must bind a numerical net")


def _check_schema(validator, payload):
    error = next(validator.iter_errors(payload), None)
    if error:
        raise ValueError(f"{error.json_path}: {error.message}")
    _check_finite(payload)

def _validate_dimensions(payload, network):
    basis = payload["native_normalization"]
    if any(basis["reference_scope"][field] != payload[field] for field in ("project_id", "network_version")):
        raise ValueError("Native reference scope differs from the output project/network")
    denominator_scale(basis)
    if network is not None:
        if (not isinstance(network, dict) or network.get("format") != "reaction-network/1"
                or any(network.get(k) != v for k, v in basis["reference_scope"].items())):
            raise ValueError("Supplied network does not match the physical reference scope")
        check_version(network, "network_version")
        catalog = network.get("catalog")
        if not isinstance(catalog, dict) or not isinstance(catalog.get("sites"), list):
            raise ValueError("Supplied network has no site catalog")
        if not all(isinstance(site, dict) and isinstance(site.get("site_id"), str) for site in catalog["sites"]):
            raise ValueError("Invalid site identity in the supplied network")
        sites = _index(catalog["sites"], "site_id")
        declared = set(basis.get("inventory_ids", []))
        for row in payload["reaction_rates"]:
            declared.update(row["sites_consumed"], row["sites_released"])
        unknown = declared - sites.keys()
        if unknown:
            raise ValueError(f"Unknown site inventories in the supplied network: {sorted(unknown)}")
    rates = _index(payload["reaction_rates"], "reaction_id")
    coefficients = _index(payload.get("rate_coefficients", []), "reaction_id")
    for rid, pair in coefficients.items():
        if rid not in rates:
            raise ValueError(f"Coefficient has no matching reaction: {rid}")
        for direction in ("forward", "reverse"):
            record = pair[direction]
            flux = rates[rid][direction]
            if isinstance(record, dict):
                if flux == "not_applicable":
                    raise ValueError("A coefficient was supplied for an excluded direction")
                convert_coefficient(record["value"], record["unit"], record["unit"], record["activity_orders"])
            elif record == "not_applicable" and flux not in (None, "not_applicable"):
                raise ValueError("A directional flux was supplied for an excluded coefficient")


def validate_conversion_bases(source_basis, target_basis, evidence=None):
    """Validate the complete physical conversion request before applying it to rates."""
    validator = _validator("2.1.0")

    def check_part(name, obj):
        ref = validator.schema["$id"] + "#/$defs/" + name
        _check_schema(validator.evolve(schema={"$ref": ref}), obj)

    check_part("normalization", source_basis)
    check_part("normalization", target_basis)
    if evidence is not None:
        check_part("conversion_evidence", evidence)


def convert_native_rate(value, quantity_kind, source_basis, target_basis, *, evidence=None):
    """Explicit 2.1 conversion for one rate."""
    validate_conversion_bases(source_basis, target_basis, evidence)
    return convert_checked_rate(value, quantity_kind, source_basis, target_basis, evidence)


def validate_rate_output_v2(payload, *, network=None):
    """Validate the explicitly selected V2 revision without resolving artifact paths. network is a legacy site catalog only."""
    version = payload.get("schema_version") if isinstance(payload, dict) else None
    if version not in ("2.0.0", "2.1.0"):
        raise ValueError("schema_version must explicitly select 2.0.0 or 2.1.0")
    _check_schema(_validator(version), payload)
    if version == "2.1.0":
        _validate_dimensions(payload, network)
    elif network is not None:
        raise ValueError("Explicit network inventory validation requires 2.1.0")
    if "output_binding" in payload:
        _index(payload["output_binding"]["native_inputs"], "path")

    conditions = payload["conditions"]
    partials = conditions["partial_pressures"]
    if partials is not None:
        _index(partials, "species_id")
        total = _sum(row["pressure_Pa"] for row in partials)
        if total > conditions["pressure_Pa"] and not _matches(total, conditions["pressure_Pa"]):
            raise ValueError("Partial pressures exceed the total pressure")
    bounds = payload["validity_range"]
    if bounds is not None:
        for field in ("temperature_K", "pressure_Pa"):
            if not bounds["min_" + field] <= conditions[field] <= bounds["max_" + field]:
                raise ValueError(f"{field} is outside the declared validity range")

    rates = payload["reaction_rates"]
    _index(rates, "reaction_id")
    _index(rates, "parameter_set_id")
    for row in rates:
        _check_progress(row)
    expected = generate_source_terms(rates)
    for group, results in source_residuals(expected, payload["source_terms"]).items():
        for identity, result in results.items():
            if not result["consistent"]:
                raise ValueError(f"source_terms.{group}.{identity}: inconsistent source rate")


class RateIdentityError(ValueError):
    """A network-qualified rate record lacks a verifiable output identity."""


def read_bound_rate_network(payload, network_path, *, reaction_ids=None, expected_network_sha256=None):
    """Qualify a V2.1 record against exact network bytes and an optional explicit subset."""
    if not isinstance(payload, dict) or payload.get("schema_version") != "2.1.0" or network_path is None:
        raise ValueError("Network qualification requires V2.1 and a network artifact")
    raw = Path(network_path).read_bytes()
    digest = sha256_bytes(raw)
    if expected_network_sha256 is not None and digest != expected_network_sha256:
        raise ValueError("Network file differs from independent rate evidence")
    network = decode_unique_json(raw)
    if not isinstance(network, dict):
        raise ValueError("Expected a network object")
    validate_rate_output_v2(payload, network=network)
    if digest != payload["provenance"]["network"]["sha256"]:
        raise ValueError("Network artifact SHA-256 differs from the rate output provenance")
    validate_bound_rows(payload, network, reaction_ids)
    binding = payload.get("output_binding")
    if not binding:
        raise RateIdentityError("Network qualification requires output dataset and run identity")
    if binding["dataset_id"].startswith("rates-"):
        unsigned = {key: value for key, value in binding.items() if key != "dataset_id"}
        if binding["dataset_id"] != "rates-" + sha256_json(dict(payload, output_binding=unsigned)):
            raise RateIdentityError("Rate output dataset identity differs from its content")
    return network


def validate_network_bound_rate_output(payload, network_path, *, reaction_ids=None):
    read_bound_rate_network(payload, network_path, reaction_ids=reaction_ids)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="path to a kinetic-rate-output/2 JSON document")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--catalog-network", "--network", dest="network", type=Path, help="legacy 2.1 site-catalog check")
    mode.add_argument("--qualified-network", type=Path, help="bind every rate row to this exact network artifact")
    parser.add_argument("--reaction-id", action="append", help="expected reaction in a qualified subset (repeatable)")
    args = parser.parse_args(argv)
    try:
        payload = read_unique_json(args.output)
        if args.reaction_id and not args.qualified_network:
            parser.error("--reaction-id requires --qualified-network")
        if args.qualified_network:
            validate_network_bound_rate_output(payload, args.qualified_network, reaction_ids=args.reaction_id)
            print("Network-qualified V2.1 rate output")
            return 0
        network = read_unique_json(args.network) if args.network else None
        validate_rate_output_v2(payload, network=network)
        if args.network and sha256_file(args.network) != payload["provenance"]["network"]["sha256"]:
            raise ValueError("Network artifact SHA-256 differs from the rate output provenance")
    except (ValueError, OSError, RuntimeError, OverflowError) as exc:
        parser.exit(1, f"Invalid V2 kinetic rate output: {exc}\n")
    scope = "site catalog" if args.network else "shape and arithmetic"
    print(f"Kinetic rate output conforms to {payload['schema_version']} ({scope})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
