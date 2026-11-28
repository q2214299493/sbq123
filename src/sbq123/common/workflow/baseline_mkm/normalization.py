"""Resolve the reviewed CATKINAS native denominator before qualifying physical rates."""
import re
from pathlib import Path

from scripts.runtime_resources import SOURCE_ROOT
from scripts.artifact_io import require_sha256, sha256_bytes
from scripts.kinetic_parameters.rate_normalization import denominator_scale
from scripts.multiphase_contracts import decode_unique_json, read_unique_json
from scripts.scientific_validation import finite_number

LEGACY_REQUEST = "one_event_per_reference_site"
REFERENCE_FIELDS = {"reference_basis", "reference_id", "denominator_value", "denominator_unit",
                    "inventory_ids", "sites_per_reference", "extent_unit", "time_unit"}
NATIVE_RATE_UNIT = "model-native rate (physical denominator unavailable)"


def read_profile(path, network, config=None, *, analysis_mass=False):
    """Return presentation options and the definition authenticated by the network."""
    if path is None:
        if config and config.get("turnover_basis"):
            raise ValueError("Verified normalization required for requested physical TOF")
        return {}, None
    path = Path(path)
    opt = read_unique_json(path)
    if not isinstance(opt, dict):
        raise ValueError("Expected a normalization profile object")
    if analysis_mass:
        from sbq123.common.evidence.mkm_mass import MASS_OPTIONS

        _check_options({k: v for k, v in opt.items() if k not in MASS_OPTIONS}, network)
    else:
        _check_options({k: v for k, v in opt.items() if k != "mass_conversion_approval"}, network)
    source = opt["source"]
    raw = (path.parent / source["path"]).read_bytes()
    if sha256_bytes(raw) != source["sha256"]:
        raise ValueError("Changed normalization evidence")
    require_verified_source(source["sha256"], network)
    contract = _definition(decode_unique_json(raw), opt, network, (config or {}).get("turnover_basis"))
    return opt, contract


def _check_options(opt, network):
    scalar = {
        "reference_mol_per_catalyst_m2",
        "reference_mol_per_kg",
        "reference_mol_per_reactor_m3",
        "catalyst_m2_per_kg",
        "catalyst_kg_per_reactor_m3",
    }
    groups = {"site_density_mol_per_surface_m2", "sites_per_reference", "feed_inlet_per_reference_s"}
    known = scalar | groups | REFERENCE_FIELDS | {"network_version", "source", "reference_basis", "target_products"}
    if opt.keys() - known or opt.get("network_version") != network["network_version"]:
        raise ValueError("Unknown analysis option or mismatched network")
    for key in (scalar | groups) & opt.keys():
        if key in groups and not isinstance(opt[key], dict):
            raise ValueError(f"Invalid normalization table: {key}")
        values = opt[key].values() if key in groups else [opt[key]]
        for v in values:
            if finite_number(v, key, nonnegative=True) == 0 and key != "feed_inlet_per_reference_s":
                raise ValueError(f"{key} requires a positive value")


def _definition(evidence, profile, network, requested):
    if not isinstance(evidence, dict):
        raise ValueError("Expected reviewed normalization evidence object")
    definition = evidence.get("normalization", evidence)
    digest = profile["source"]["sha256"]
    if "normalization" not in evidence and not REFERENCE_FIELDS.intersection(evidence):
        definition = _archived_reference(digest)
    if not isinstance(definition, dict) or not REFERENCE_FIELDS <= definition.keys():
        raise ValueError("Incomplete reviewed normalization definition")
    version = network["network_version"]
    if definition.get("network_version", version) != version:
        raise ValueError("Reviewed normalization network version differs")
    sites = [s["site_id"] for s in network["catalog"]["sites"]]
    contract = {key: definition[key] for key in sorted(REFERENCE_FIELDS)}
    contract.update(network_version=version, evidence_sha256=digest)
    validate_reference(contract, sites, version, requested)
    # Validate the profile's repeated fields as well: True and 1 compare equal in Python.
    supplied = contract | {key: profile[key] for key in REFERENCE_FIELDS & profile.keys()}
    validate_reference(supplied, sites, version, requested)
    for record in (contract, supplied):
        record["inventory_ids"] = sorted(record["inventory_ids"])
    if supplied != contract:
        raise ValueError("Profile conflicts with reviewed normalization definition")
    return contract


def _archived_reference(digest):
    """Read the original numeric contract for pre-contract evidence with a prose definition."""
    folder = SOURCE_ROOT / "reports/multiphase/stage_b1_4"
    archived = read_unique_json(folder / "catkinas_qualification.json")["phase3_0"]
    if digest != archived["reference"]["sha256"]:
        raise ValueError("Missing structured, reviewed normalization evidence")
    basis = read_unique_json(folder / "replay/catkinas-phase3_0.json")["native_normalization"]
    return dict(basis, reference_basis=basis["basis_kind"], sites_per_reference=archived["sites_per_reference"])


def normalization(path, network, config=None):
    return read_profile(path, network, config)[1]


def require_verified_source(digest, network):
    require_sha256(digest, label="normalization evidence")
    if not any(row["role"] == "verified_evidence" and row["sha256"] == digest for row in network["source_artifacts"]):
        raise ValueError("Normalization source lacks matching verified network evidence")


def validate_reference(ref, sites, version, requested=None):
    """Validate a contract stored in a plan/result, including the explicit unit of native rates."""
    if not isinstance(ref, dict) or not (REFERENCE_FIELDS | {"network_version", "evidence_sha256"}) <= ref.keys():
        raise ValueError("Incomplete normalization contract")
    if ref["network_version"] != version or ref["extent_unit"] != "event" or ref["time_unit"] != "s":
        raise ValueError("Invalid normalization network or native event/time units")
    kind = ref["reference_basis"]
    if kind not in ("reference_site", "reference_site_pair", "other") or requested not in (None, LEGACY_REQUEST, kind):
        raise ValueError("Requested turnover basis conflicts with reviewed normalization")
    if requested == LEGACY_REQUEST and kind != "reference_site":
        legacy = _archived_reference(ref["evidence_sha256"])
        if any(ref[field] != legacy[field] for field in REFERENCE_FIELDS):
            raise ValueError("Legacy turnover request conflicts with archived reference")
    if not all(isinstance(ref[k], str) and ref[k].strip() for k in ("reference_id", "denominator_unit")):
        raise ValueError("Normalization requires an explicit reference ID and denominator unit")
    if type(ref["denominator_value"]) not in (int, float):
        raise ValueError("Normalization denominator must be numeric")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", ref["reference_id"]):
        raise ValueError("Invalid normalization reference ID")
    require_sha256(version, label="normalization network version")
    require_sha256(ref["evidence_sha256"], label="normalization evidence")
    finite_number(ref["denominator_value"], "normalization denominator", positive=True)
    denominator_scale(dict(ref, basis_kind=kind))
    counts, ids = ref["sites_per_reference"], ref["inventory_ids"]
    if not isinstance(counts, dict) or not counts or not isinstance(ids, list) or len(ids) != len(counts):
        raise ValueError("Invalid normalization inventory")
    if not all(isinstance(site, str) and site.strip() for site in ids):
        raise ValueError("Invalid normalization inventory IDs")
    if set(ids) != set(counts) or not set(ids) <= set(sites):
        raise ValueError("Normalization inventory IDs differ from counts or network")
    if any(type(n) is not int or n < 1 for n in counts.values()):
        raise ValueError("Normalization site counts must be positive integers")
    size = {"reference_site": 1, "reference_site_pair": 2}.get(kind)
    if size is not None and sum(counts.values()) != size:
        raise ValueError(f"{kind} requires {size} individual sites per reference unit")


def reference_rate(native, ref):
    """Convert a native event rate over the declared denominator to one reference unit."""
    if native is None or ref is None:
        return None
    return finite_number(native / ref["denominator_value"], "rate per reviewed reference unit")


def individual_rate(per_reference, ref):
    """Mean over the explicitly counted individual sites in one reviewed unit."""
    return per_reference / sum(ref["sites_per_reference"].values()) if per_reference is not None and ref else None


def flux_unit(ref):
    if not ref:
        return NATIVE_RATE_UNIT
    value = ref["denominator_value"]
    prefix = "" if value == 1 else f"{value} "
    return f"events per {prefix}{ref['denominator_unit']} per second"
