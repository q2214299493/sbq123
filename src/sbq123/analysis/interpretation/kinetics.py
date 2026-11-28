"""Evidence-qualified interpretation of native point, window and perturbation results."""
from copy import deepcopy

from sbq123.common.kinetic_model.contracts import identity


def interpret_point(analysis, expected_sha256):
    """expected_sha256 is retained separately by the current MKM analysis producer."""
    report = deepcopy(analysis)
    if identity(report) != expected_sha256 or report.get("status") != "analyzed" or "mass_normalization" not in report:
        raise ValueError("Current MKM analysis with a separately retained producer identity required")
    sites = []
    for site, row in report["utilization"].items():
        sites.append(dict(inventory=site, occupied_fraction=row.get("occupied_fraction"),
                          vacancy_fraction=row.get("vacancy_fraction"), competitors=row.get("competitors"),
                          contributions=row.get("contributions"), evidence=expected_sha256))
    return dict(source_sha256=expected_sha256, source_hashes=report["source_hashes"], scope=report["scope"],
                direct_observations=dict(coverage=report["coverage"], site_inventories=sites, tof=report["tof"],
                                         selectivity=report["selectivity"], mass=report["mass_normalization"]),
                supported_explanation="Adsorbates on the same inventory share its finite capacity."
                                      if any(len(s["competitors"] or []) > 1 for s in sites) else None,
                alternative_explanation="A high occupancy can reflect slow removal or fast replenishment.",
                mechanism_hypothesis=None, prediction_requiring_validation=None,
                limitation="One steady point cannot resolve temperature trends or establish a rate-controlling step.")


def interpret_window(window, expected_sha256):
    """Read a producer-retained window_bridge report, preserving its time and cell references."""
    window = deepcopy(window)
    digest = window.pop("record_sha256")
    # The historical writer owns the JSON canonicalization of this record.
    from sbq123.common.artifacts.artifact_io import sha256_json
    if window.get("format") != "kmc-window-integration/1" or digest != expected_sha256 or sha256_json(window) != digest:
        raise ValueError("KMC window differs from retained bridge receipt")
    return dict(source_sha256=digest, manifest_sha256=window["manifest_sha256"],
                direct_observations=window["observations"], statistics=window["statistics"],
                basis=window["rate_output"]["native_normalization"], window=window["window"]["definition"],
                scope=window["statistics"]["scope"], validity_range=window["rate_output"]["validity_range"],
                supported_explanation="Coverage integrates occupied sites over the sampled window.",
                alternative_explanation="Initial transients, finite cell size and sampling can affect an apparent trend.",
                mechanism_hypothesis=None, prediction_requiring_validation="Compare matched independent seeds and cell sizes.",
                limitation="Window statistics only support the reported observation span.")


def archived_study(root, objective_id):
    from sbq123.discovery.ranking.scientific_priority.benchmark import synthetic

    pin = "358c8037a4ecb3c5e0fffd137a4d7068e26c0e81c38c9584be3fbbf7cb0eb8ca"
    data, objectives = synthetic(root, expected_fixture_sha256=pin)
    return data, objectives[objective_id], pin


def interpret_sensitivity(root, objective_id="activity"):
    """Report the signed local derivatives from the released benchmark perturbation study."""
    data, objective, expected_sha256 = archived_study(root, objective_id)
    scope = objective["scope"]
    rows = []
    for metric in data["metrics"] + data["context_evidence"]:
        if metric["kind"] not in ("ts_drc", "intermediate_G", "gas_order", "selectivity_sensitivity"):
            continue
        if metric["scope"] != scope or (metric["kind"] != "gas_order" and metric["observable"] != objective["observable"]):
            continue
        source = data["sources"][metric["source"]]
        rows.append(dict(kind=metric["kind"], parameter=metric["parameter"], value=metric["value"],
                         coordinate=metric.get("coordinate", metric.get("constraint")),
                         observable=metric["observable"], source_sha256=source["sha256"]))
    from sbq123.common.workflow.multiphase_contracts import read_artifact
    batch_ref = data["sources"]["batch"]
    batch, _ = read_artifact(root / batch_ref["path"], expected_sha256=batch_ref["sha256"])
    existing = {r["parameter"] for r in rows if r["kind"] == "ts_drc"}
    for rid, item in batch["reactions"].items():
        if rid not in existing and item.get("stability") == "stable" and item.get("drc") is not None:
            rows.append(dict(kind="ts_drc", parameter=rid, value=item["drc"], coordinate="G_over_kBT",
                             observable=objective["observable"], source_sha256=batch_ref["sha256"]))
    control = [r for r in rows if r["kind"] == "ts_drc"]
    return dict(source_sha256=expected_sha256, scope=scope, direct_observations=rows,
                supported_explanation="The signed TS derivatives quantify local control of the specified observable."
                                      if control else None,
                alternative_explanation="Coverage redistribution may contribute to the perturbed response.",
                mechanism_hypothesis=None, prediction_requiring_validation="Repeat perturbations on the same branch at another state.",
                limitation="Local derivatives depend on the perturbation coordinate, feed constraint and branch.")
