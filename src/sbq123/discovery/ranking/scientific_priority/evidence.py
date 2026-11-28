"""Read-only evidence matching and model-specific reliability assessment."""

from contextlib import closing
from pathlib import Path
import re
import sqlite3

from sbq123.common.validation.scientific_validation import finite_number


OPERATIONS = {
    "electronic_energy": "DFT single-point energy",
    "minimum_geometry": "DFT geometry optimization",
    "force_label": "DFT force evaluation",
    "vibrations": "DFT frequency calculation",
    "reaction_path": "NEB",
    "saddle_refinement": "DIMER",
    "candidate_geometry": "MLIP candidate structure generation",
    "training_labels": "MLIP fine-tuning data acquisition",
    "validation_set": "Additional validation dataset generation",
}


def digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def registry_inventory(database, hashes):
    """Discover calculations via exact file identities. A shared input alone cannot qualify a result."""
    if not hashes or not all(map(digest, hashes)):
        raise ValueError("Valid target structure hashes required")
    found = {}
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        for key in sorted(set(hashes)):
            hits = []
            for row in db.execute(
                """SELECT DISTINCT c.calculation_id,c.module,c.purpose,f.role
                FROM files f JOIN calculations c ON c.calculation_id=f.calculation_id
                WHERE f.sha256=? ORDER BY c.calculation_id,f.role""",
                (key,),
            ):
                results = db.execute(
                    """SELECT result_id,result_name,unit,reference_convention,validation_status
                    FROM results WHERE calculation_id=? ORDER BY result_id""",
                    (row["calculation_id"],),
                )
                hits.append(dict(**row, results=[dict(r) for r in results]))
            found[key] = hits
    return found


def match_evidence(candidate, entries, equivalences):
    """Reuse only reviewed operation-, target- and protocol-compatible records."""
    targets = candidate["targets"]
    protocol = candidate["protocol"]
    matches = []
    if not protocol:
        return matches
    for record in entries:
        if record["protocol"] != protocol or record["need"] != candidate["need"] or record["review"] != "accepted":
            continue
        if not targets or targets.keys() != record["targets"].keys() or not all(map(digest, targets.values())):
            continue

        def equivalent(role, target):
            other = record["targets"][role]
            return target == other or any(
                e["protocol"] == protocol
                and e["review"] == "accepted"
                and e["rule"]
                and digest(e["review_sha256"])
                and {target, other} == set(e["hashes"])
                and digest(other)
                for e in equivalences
            )

        if all(equivalent(role, h) for role, h in targets.items()):
            matches.append(record["id"])
    return sorted(matches)


def novelty(record):
    """Nearest compatible training descriptor, using a declared per-feature scale."""
    space = record.get("descriptor_comparison")
    if not space:
        return record.get("structural_distance"), record.get("distance_definition")
    scales = [finite_number(s, "descriptor scale", positive=True) for s in space["scales"]]
    query = space["query"]
    if not scales or len(query) != len(scales) or not space["definition"]:
        raise ValueError("Invalid descriptor definition")
    distances = []
    for row in space["training"]:
        if row["definition"] != space["definition"]:
            continue
        if not digest(row["structure_sha256"]) or len(row["vector"]) != len(query):
            raise ValueError("Invalid training descriptor")
        distances.append(
            sum(
                ((finite_number(x, "feature") - finite_number(y, "training feature")) / s) ** 2
                for x, y, s in zip(query, row["vector"], scales, strict=True)
            )
            ** 0.5
        )
    return min(distances, default=None), space["definition"]


def reliability(candidate, records):
    applicable = [
        r
        for r in records
        if candidate.get("model_version")
        and r["model_version"] == candidate["model_version"]
        and r["targets"] == candidate["targets"]
        and r["protocol"] == candidate["protocol"]
        and r["parameter"] == candidate["parameter"]
        and r["review"] == "accepted"
    ]
    if len(applicable) > 1:
        raise ValueError("Ambiguous reliability evidence")
    r = applicable[0] if applicable else {}
    validation = {
        k: r.get("validation_errors", {}).get(k) for k in ("relative_energy_rmse_eV", "component_rmse_eV_per_A", "barrier_rmse_eV")
    }
    validation["vector_rmse_eV_per_A"] = r.get("validation_errors", {}).get("vector_rmse_eV_per_A")
    domain = r.get("extrapolation_grade")
    force_review = r.get("aqcat25_force_review")
    if force_review is not None:
        if force_review["checkpoint_sha256"] != candidate["model_version"] or not any(
            s["structure_sha256"] in candidate["targets"].values() for s in force_review["samples"]
        ):
            raise ValueError("AQCat25 force evaluation has incompatible checkpoint or sample")
        validation["vector_rmse_eV_per_A"] = force_review["metrics"]["vector_rmse_eV_per_A"]
        domain = force_review["status"]
    for k, v in validation.items():
        if v is not None:
            finite_number(v, k, nonnegative=True)
    calibration = None if domain in ("out_of_domain", "calibration_failed") else r.get("calibration")
    if calibration:
        if not calibration.get("reference") or calibration.get("distribution") != "normal_eV":
            calibration = None
        else:
            finite_number(calibration["prior_sd_eV"], "calibrated spread", nonnegative=True)
    disagreement = r.get("ensemble_sd_eV")
    if disagreement is not None:
        finite_number(disagreement, "ensemble disagreement", nonnegative=True)
    distance, definition = novelty(r)
    return dict(
        model_version=candidate.get("model_version"),
        source=r.get("source"),
        validation_errors=validation,
        calibration=calibration,
        calibration_status="calibrated" if calibration else "uncalibrated",
        ensemble_sd_eV=disagreement,
        extrapolation_grade=domain,
        coverage={
            k: r.get("coverage", {}).get(k) for k in ("training_set", "composition", "phase", "facet", "site", "reaction_coordinate")
        },
        structural_distance=distance,
        distance_definition=definition,
    )
