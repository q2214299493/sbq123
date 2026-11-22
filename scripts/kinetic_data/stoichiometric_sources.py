"""Stoichiometry and signed source rates on one caller-declared native basis."""
from __future__ import annotations

import math
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass


@dataclass(frozen=True)
class Stoichiometry:
    reaction_ids: tuple[str, ...]
    species: dict[str, dict[str, int]]
    vacancies: dict[str, dict[str, int]]


def indexed(rows, key):
    result = {}
    for row in rows:
        label = row[key]
        if label in result:
            raise ValueError(f"Duplicate {key}: {label}")
        result[label] = row
    return result


def _integer(value, label):
    if type(value) is int or (type(value) is float and value.is_integer()):
        return int(value)
    raise ValueError(f"{label} must be an integer")


def _counts(mapping, label):
    if not isinstance(mapping, dict):
        raise ValueError(f"Missing or invalid {label}")
    result = {key: _integer(value, label) for key, value in mapping.items()}
    if any(count < 1 for count in result.values()):
        raise ValueError(f"{label} coefficients must be positive")
    return result


def _matrix(reactions, ids, left, right):
    rows = {}
    for rid in ids:
        before = _counts(reactions[rid][left], f"{rid}.{left}")
        after = _counts(reactions[rid][right], f"{rid}.{right}")
        for key in before.keys() | after.keys():
            row = rows.setdefault(key, {})
            coefficient = after.get(key, 0) - before.get(key, 0)
            if coefficient:
                row[rid] = coefficient
    return dict(sorted(rows.items()))


def build_matrices(reactions):
    """Sparse labeled rows; even an exactly cancelling participant has a row."""
    records = indexed(reactions, "reaction_id")
    ids = tuple(sorted(records))
    return Stoichiometry(ids, _matrix(records, ids, "reactants", "products"),
                         _matrix(records, ids, "sites_consumed", "sites_released"))


def finite_sum(values):
    try:
        total = math.fsum(values)
    except (OverflowError, ValueError) as exc:
        raise ValueError("Rate sum exceeds the finite numeric range") from exc
    if not math.isfinite(total):
        raise ValueError("Rate sum exceeds the finite numeric range")
    return total


def _project(matrix, net):
    return {
        label: None if any(net[rid] is None for rid in row)
        else finite_sum(n * net[rid] for rid, n in row.items())
        for label, row in matrix.items()
    }


def project_progress(matrices, net):
    """Project signed, qualified net observations; no unit or denominator conversion."""
    if set(matrices.reaction_ids) != net.keys():
        raise ValueError("Net progress reaction identities differ from stoichiometry")
    for rid, value in net.items():
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
            raise ValueError(f"{rid}: expected finite net progress or None")
    return _project(matrices.species, net), _project(matrices.vacancies, net)


def generate_source_terms(reaction_rates):
    """Legacy public V2 representation; the envelope qualifies directions and evidence."""
    rows = list(reaction_rates)
    species, vacancies = project_progress(build_matrices(rows), {r["reaction_id"]: r["net"] for r in rows})
    return {
        "species": [{"species_id": key, "net_production_rate": value} for key, value in species.items()],
        "site_inventories": [{"site_id": key, "net_vacancy_rate": value} for key, value in vacancies.items()],
    }


def rate_matches(value, expected):
    if value is None or expected is None:
        return value is expected
    return math.isclose(value, expected, rel_tol=1e-12, abs_tol=0)


def source_residuals(expected, reported):
    """Reported minus projected. A matching pair of unavailable values has no numeric residual."""
    results = {}
    for group, key, field in (("species", "species_id", "net_production_rate"),
                              ("site_inventories", "site_id", "net_vacancy_rate")):
        actual = indexed(reported[group], key)
        projected = indexed(expected[group], key)
        if actual.keys() != projected.keys():
            raise ValueError(f"source_terms.{group}: identities differ from the reaction stoichiometry")
        results[group] = {}
        for label, row in projected.items():
            value, target = actual[label][field], row[field]
            delta = None if value is None or target is None else finite_sum((value, -target))
            results[group][label] = {"residual": delta, "consistent": rate_matches(value, target)}
    return results


def stoichiometric_totals(terms, vacancies):
    """Sum elements, charge and occupied-plus-vacant sites for gross or signed coefficients.

    Each term gives a molecular coefficient, composition, charge and per-molecule
    site footprint. A missing operand leaves only its own total unknown.
    """
    elements = Counter()
    charge = 0
    sites = None if vacancies is None else Counter(vacancies)
    for coefficient, composition, molecular_charge, footprint in terms:
        if composition is None:
            elements = None
        elif elements is not None:
            elements.update({key: coefficient * n for key, n in composition.items()})
        charge = None if charge is None or molecular_charge is None else charge + coefficient * molecular_charge
        if footprint is None:
            sites = None
        elif sites is not None:
            sites.update({key: coefficient * n for key, n in footprint.items()})
    return elements, charge, sites


def conservation_residuals(matrices, species_records):
    """Exact per-reaction element, charge and occupied-plus-vacant site residuals."""
    catalog = indexed(species_records, "species_id")
    composition, charge, occupancy = {}, {}, {}
    for sid, row in matrices.species.items():
        if not row:
            continue
        if sid not in catalog:
            raise ValueError(f"Missing species metadata for {sid}")
        record = catalog[sid]
        composition[sid] = _counts(record.get("composition"), f"{sid}.composition")
        if not composition[sid]:
            raise ValueError(f"Missing {sid}.composition")
        charge[sid] = _integer(record.get("charge"), f"{sid}.charge")
        occupancy[sid] = _counts(record.get("site_occupancy"), f"{sid}.site_occupancy")

    elements = sorted(set().union(*(c.keys() for c in composition.values())))
    sites = sorted(set(matrices.vacancies).union(*(c.keys() for c in occupancy.values())))
    results = {}
    for rid in matrices.reaction_ids:
        terms = ((matrices.species[sid][rid], composition[sid], charge[sid], occupancy[sid])
                 for sid in composition if rid in matrices.species[sid])
        vacancies = {site: row[rid] for site, row in matrices.vacancies.items() if rid in row}
        element_total, charge_total, site_total = stoichiometric_totals(terms, vacancies)
        results[rid] = {
            "elements": {e: element_total[e] for e in elements},
            "charge": charge_total,
            "inventories": {q: site_total[q] for q in sites},
        }
    return results


def _checked_covariance(values, labels):
    """Check a full labeled covariance, including singular positive-semidefinite matrices."""
    import numpy as np

    raw = np.asarray(values, dtype=object)
    if raw.shape != (len(labels), len(labels)):
        raise ValueError("Covariance shape must match both reaction axes")
    if any(isinstance(x, (bool, np.bool_)) or not isinstance(x, (int, float, np.integer, np.floating)) for x in raw.flat):
        raise ValueError("Covariance entries must be finite real numbers")
    matrix = raw.astype(float)
    if not np.isfinite(matrix).all() or not np.array_equal(matrix, matrix.T):
        raise ValueError("Covariance must be finite and symmetric")
    diagonal = matrix.diagonal()
    if (diagonal < 0).any() or (matrix[diagonal == 0] != 0).any():
        raise ValueError("Negative variance or nonzero covariance with a zero variance")
    positive = diagonal > 0
    if positive.any():
        # Correlations make the PSD tolerance independent of individual rate scales.
        scales = np.sqrt(diagonal[positive])
        with np.errstate(over="ignore", invalid="ignore"):
            corr = matrix[np.ix_(positive, positive)] / np.maximum.outer(scales, scales) / np.minimum.outer(scales, scales)
        tol = 16 * len(scales) * np.finfo(float).eps
        if not np.isfinite(corr).all() or abs(corr).max() > 1 + tol or np.linalg.eigvalsh(corr)[0] < -tol:
            raise ValueError("Covariance must be positive semidefinite")
    return {a: dict(zip(labels, row.tolist(), strict=True)) for a, row in zip(labels, matrix, strict=True)}


def _covariance_entry(left, right, covariance, variances):
    if variances is not None:
        shared = left.keys() & right.keys()
        if any(variances[r] is None for r in shared):
            return None
        return finite_sum(left[r] * right[r] * variances[r] for r in sorted(shared))
    return finite_sum(n * m * covariance[a][b] for a, n in left.items() for b, m in right.items())


def source_covariance(matrices, native_normalization, *, covariance=None, reaction_ids=None, independent_variances=None):
    """Project net-progress uncertainty on the same native basis; both covariance axes carry the same labels."""
    axes, rows = [], []
    extent = native_normalization["extent_unit"]
    for role, matrix, unit in (("species_source", matrices.species, "molecule"), ("site_source", matrices.vacancies, "vacancy")):
        for label, row in matrix.items():
            axes.append({"quantity": role, "id": label, "numerator_unit": unit if extent == "event" else extent})
            rows.append(row)
    result = {"axes": axes, "native_normalization": deepcopy(native_normalization), "covariance": None}
    if covariance is not None:
        if independent_variances is not None:
            raise ValueError("Supply full covariance or explicitly independent variances")
        if reaction_ids is None:
            raise ValueError("Full covariance requires reaction identities on both axes")
        labels = tuple(reaction_ids)
        if len(set(labels)) != len(labels) or set(labels) != set(matrices.reaction_ids):
            raise ValueError("Covariance reaction identities differ from stoichiometry")
        covariance = _checked_covariance(covariance, labels)
    elif reaction_ids is not None:
        raise ValueError("reaction_ids label the axes of a full covariance")
    elif independent_variances is not None:
        if independent_variances.keys() != set(matrices.reaction_ids):
            raise ValueError("Independent variance reaction identities differ from stoichiometry")
        for rid, value in independent_variances.items():
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
                raise ValueError(f"{rid}: expected a finite nonnegative independent variance or None")
    else:
        return result
    projected = [[_covariance_entry(a, b, covariance, independent_variances) for b in rows] for a in rows]
    for i, axis in enumerate(axes):
        if projected[i][i] is not None and projected[i][i] < 0:
            raise ValueError(f"Negative propagated variance for {axis['quantity']} {axis['id']}")
    result["covariance"] = projected
    return result
