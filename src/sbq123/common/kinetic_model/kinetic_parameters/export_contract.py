from sbq123.common.artifacts.artifact_io import check_version
from sbq123.common.kinetic_model.kinetic_parameters.laws import MOLECULAR_ACTIVITY
from sbq123.common.kinetic_model.kinetic_parameters.laws import positive, pressure_unit


def validate_export(dataset, *, fixed_mkm=False):
    check_version(dataset, "dataset_version")
    if "coverage_iteration" in dataset and not fixed_mkm:
        raise ValueError("Expected an unmodified parent or a fixed MKM consumer; no qualified lattice-event export")
    if (dataset.get("format") != "kinetic-dataset/1" or not dataset["export_eligible"] or not dataset["reactions"]
            or any(not r["export_eligible"] or r["missing"] for r in dataset["reactions"])):
        raise ValueError("Kinetic dataset is blocked for export")
    conditions, fractions = set(), {}
    for r in dataset["reactions"]:
        p = r["parameter_set"]
        if not fixed_mkm and p["standard_states"]["surface_activity_convention"] == MOLECULAR_ACTIVITY:
            raise ValueError("Molecular reference activity is qualified only for offline MKM mapping")
        conditions.add((r["model"].get("use_scope", "project"), p["temperature_K"], p["pressure_Pa"], p["standard_state_id"],
                        p["standard_states"]["gas_pressure_Pa"], p["standard_states"]["surface_activity_convention"]))
        for sid, theta in r["model"].get("coverage_fractions", {}).items():
            if fractions.setdefault(sid, theta) != theta:
                raise ValueError("Conflicting coverage conditions in one export")
    if len(conditions) != 1:
        raise ValueError("A parameter export requires a common temperature, pressure and standard state")


def per_bar(rate, p0, factor=1):
    order = sum(rate["gas_orders"].values())
    k = rate["activity_coefficient_s^-1"] * (100000 / p0) ** order / factor
    return {"coefficient": positive(k, "converted rate"), "unit": pressure_unit(order, "bar"),
            "gas_partial_pressure_orders": rate["gas_orders"]}


def source_info(row):
    model = row["model"]
    source = {"parameter_set_id": row["parameter_set"]["parameter_set_id"], "sources": model["sources"],
            "review_subject": model["scientific_review"]["subject_sha256"], "use_scope": model.get("use_scope", "project")}
    if "coverage_energy" in row:
        source["coverage_energy"] = row["coverage_energy"]
    if "prediction" in row:
        source["energy_prediction"] = row["prediction"]
    return source
