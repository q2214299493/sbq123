"""Read-only V2 reaction progress and stoichiometric source terms on one native basis."""
from __future__ import annotations

import argparse
import math
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from scripts.multiphase_contracts import _check_finite, read_unique_json
from scripts.runtime_resources import resource_path


@lru_cache(maxsize=1)
def _validator():
    names = ("kinetics/rate_output_v2", "kinetics/rate_source_terms_v2", "catalysis/common",
             "kinetics/reaction", "kinetics/kinetic_parameter", "kinetics/simulation_run")
    schemas = [read_unique_json(resource_path(f"configs/{name}.schema.json")) for name in names]
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    )
    return Draft202012Validator(schemas[0], registry=registry)


def _sum(values):
    try:
        total = math.fsum(values)
    except (OverflowError, ValueError) as exc:
        raise ValueError("Rate sum exceeds the finite numeric range") from exc
    if not math.isfinite(total):
        raise ValueError("Rate sum exceeds the finite numeric range")
    return total


def generate_source_terms(reaction_rates):
    """Project schema-conforming progress rates onto species and vacant site inventories."""
    species = defaultdict(list)
    vacancies = defaultdict(list)
    for row in reaction_rates:
        for left, right, terms in ((row["reactants"], row["products"], species),
                                   (row["sites_consumed"], row["sites_released"], vacancies)):
            for identity in left.keys() | right.keys():
                change = right.get(identity, 0) - left.get(identity, 0)
                terms[identity].append(change * row["net"])
    return {
        "species": [{"species_id": sid, "net_production_rate": _sum(species[sid])}
                    for sid in sorted(species)],
        "site_inventories": [{"site_id": site, "net_vacancy_rate": _sum(vacancies[site])}
                             for site in sorted(vacancies)],
    }


def _index(rows, key):
    result = {row[key]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"Duplicate {key}")
    return result


def _matches(value, expected):
    # Relative serialization tolerance only; preserve the distinction between zero and a small signal.
    return math.isclose(value, expected, rel_tol=1e-12, abs_tol=0.0)


def validate_rate_output_v2(payload):
    """Validate the declared V2 shape, bindings and arithmetic without resolving artifact paths."""
    error = next(_validator().iter_errors(payload), None)
    if error:
        raise ValueError(f"{error.json_path}: {error.message}")
    _check_finite(payload)

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
        if not _matches(row["net"], row["forward"] - row["reverse"]):
            raise ValueError(f"{row['reaction_id']}: net must equal forward minus reverse")
    expected = generate_source_terms(rates)
    for group, key, field in (("species", "species_id", "net_production_rate"),
                              ("site_inventories", "site_id", "net_vacancy_rate")):
        reported = _index(payload["source_terms"][group], key)
        if reported.keys() != {row[key] for row in expected[group]}:
            raise ValueError(f"source_terms.{group}: identities differ from the reaction stoichiometry")
        for row in expected[group]:
            if not _matches(reported[row[key]][field], row[field]):
                raise ValueError(f"source_terms.{group}.{row[key]}: inconsistent {field}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="path to a kinetic-rate-output/2 JSON document")
    args = parser.parse_args(argv)
    try:
        validate_rate_output_v2(read_unique_json(args.output))
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Invalid V2 kinetic rate output: {exc}\n")
    print("Kinetic rate output conforms to 2.0.0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
