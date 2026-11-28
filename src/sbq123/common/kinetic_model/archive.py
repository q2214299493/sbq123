"""Read an evidence-registered V3.1 rate model without expanding its operating domain."""

import io
import json
from hashlib import sha256
from importlib.resources import files
from pathlib import PurePosixPath
import zipfile

from sbq123.common.evidence._records import entry
from sbq123.common.kinetic_model.contracts import GAS_CONSTANT, Model, identity


def read_registered_cycle():
    replay = entry("replay", "v31-b1")
    directory = files("sbq123.common").joinpath("resources")

    def load(ref):
        path, sep, member = ref["path"].partition("!/")
        if PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts:
            raise ValueError("Invalid replay locator")
        data = directory.joinpath(*PurePosixPath(path).parts).read_bytes()
        if sep:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if archive.namelist().count(member) != 1:
                    raise ValueError("Ambiguous replay member")
                data = archive.read(member)
        if sha256(data).hexdigest() != ref["sha256"]:
            raise ValueError("Replay evidence digest mismatch")
        return json.loads(data)

    rows = load(replay)["replay"]["catkinas"]["runs"]
    network_refs = {tuple(sorted(r["provenance"]["network"].items())) for r in rows}
    data_refs = {tuple(sorted(r["provenance"]["dataset"].items())) for r in rows}
    if len(network_refs) != 1 or len(data_refs) != 1:
        raise ValueError("Ambiguous historical kinetic model")
    network = load(dict(network_refs.pop()))
    rates = load(dict(data_refs.pop()))
    return _convert_network(network, rates, scope="synthetic_benchmark", provenance=replay["scope"])


def from_network(network, rates, *, scope="project"):
    return _convert_network(network, rates, scope=scope, provenance="user_supplied")


def _convert_network(network, rates, *, scope, provenance):
    raw = network_record(network, rates, scope=scope)
    return Model._from_verified_record(raw, registered_digest=identity(raw), provenance=provenance)


def network_record(network, rates, *, scope):
    """Convert eligible, point-specific ideal-gas activity laws without extrapolation."""
    for record, field in ((network, "network_version"), (rates, "dataset_version")):
        if identity({k: v for k, v in record.items() if k != field}) != record[field]:
            raise ValueError("Invalid source version for " + field)
    if network["network_version"] != rates["network_version"] or not rates["export_eligible"]:
        raise ValueError("Kinetic model differs from qualified network")
    species = [
        dict(name=s["species_id"], phase=s["phase"], elements=s["composition"], charge=s["charge"], sites=s["site_occupancy"])
        for s in rates["species"]
    ]
    sites = sorted({site for s in species for site in s["sites"]})
    defs = {r["definition"]["reaction_id"]: r["definition"] for r in network["reactions"]}
    conditions = set()
    steps = []
    for reaction in rates["reactions"]:
        if (
            not reaction["scientifically_validated"]
            or not reaction["export_eligible"]
            or reaction["model"].get("use_scope", "project") != scope
        ):
            raise ValueError("Unqualified archived reaction")
        if reaction["model"].get("coverage_fractions"):
            raise ValueError("Coverage-dependent barriers require their reviewed evaluator")
        param = reaction["parameter_set"]
        t, p = param["temperature_K"], param["pressure_Pa"]
        conditions.add((t, p))
        d = defs[reaction["reaction_id"]]
        change = {s: d["products"].get(s, 0) - d["reactants"].get(s, 0) for s in d["products"].keys() | d["reactants"].keys()}
        for direction, sign in [("forward", 1), ("reverse", -1)]:
            law = reaction["rates"].get(direction)
            if law is None:
                continue
            exponent = sum(law["gas_orders"].values())
            factor = (GAS_CONSTANT * t / param["standard_states"]["gas_pressure_Pa"]) ** exponent
            orders = law["activity_orders"]
            steps.append(
                dict(
                    change={k: sign * v for k, v in change.items()},
                    orders={**orders["species"], **orders["vacant_sites"]},
                    coefficient=law["activity_coefficient_s^-1"] * factor,
                    activation_J_mol=0.0,
                )
            )
    if len(conditions) != 1:
        raise ValueError("Inconsistent coefficient domain")
    t, p = conditions.pop()
    raw = dict(
        schema_version=1,
        species=species,
        sites=sites,
        steps=steps,
        reference_temperature_K=t,
        temperature_domain_K=[t, t],
        pressure_domain_Pa=[p, p],
        rate_basis="mol_per_mol_site_s",
    )
    return raw
