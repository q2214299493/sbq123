"""Directional and species fluxes for either independently reviewed rate-output role."""
from copy import deepcopy
from math import fsum

from sbq123.common.evidence.kinetic_data import analysis_evidence as owner


def directional_sources(rows):
    """Count actual molecules on each side, including turnover of cancelling participants."""
    species = sorted({sid for r in rows for side in ("reactants", "products") for sid in r[side]})
    result = {}
    for sid in species:
        def gross(producing):
            terms = []
            for r in rows:
                for direction, side in (("forward", "products"), ("reverse", "reactants")):
                    if not producing:
                        side = "reactants" if side == "products" else "products"
                    count = r[side].get(sid, 0)
                    if count:
                        if r[direction] == "not_applicable":
                            continue
                        if type(r[direction]) not in (int, float):
                            return None
                        terms.append(count * r[direction])
            return fsum(terms)

        result[sid] = {"gross_production": gross(True), "gross_consumption": gross(False)}
    return result


def analyze_rates(role, path, *, expected_sha256):
    """Read original reviewed bytes; the supplied digest only selects the release-owned receipt."""
    from sbq123.common.evidence.kinetic_data.observations import rate_observation
    from sbq123.common.workflow.multiphase_contracts import read_artifact

    family, row = owner.approved_replay_row(expected_sha256)
    rates, digest = read_artifact(path, expected_sha256=row["output_sha256"])
    if {"catkinas": "mkm", "zacros": "kmc"}.get(family.lower()) != role:
        raise ValueError("Rate evidence belongs to another engine")
    evidence = {"path": path, "sha256": digest}
    native = rates["native_normalization"]
    observation = rate_observation(rates, owner.review_path(row, row["provenance"]["network"], role),
                                   conditions=rates["conditions"], target=native, rate_evidence=evidence)
    if observation.get("status") == "insufficient_evidence":
        return observation
    sources = directional_sources(rates["reaction_rates"])
    for sid, values in sources.items():
        values["net_production"] = observation["values"][sid]["value"]
    return dict(observation=observation, elementary_rates=deepcopy(rates["reaction_rates"]),
                species_sources=sources, basis=native,
                species_numerator="molecule" if native["extent_unit"] == "event" else native["extent_unit"],
                qualification=observation["evidence_scope"], uncertainty=rates.get("uncertainty"),
                rate_control=None, rate_control_reason="Directional flux alone does not determine a response derivative")
