"""Shared experiment specifications and limits for a bounded sensitivity study."""

from scripts.baseline_mkm.sensitivity_inputs import FIXED_OTHERS, FIXED_TOTAL
from scripts.scientific_validation import finite_number

LIMITS = dict(max_runs=8, per_run_s=210, native_s=1680, wall_s=1920, max_parallel=1, max_retries=0)


def specifications(experiments):
    if not experiments or experiments.keys() - {"intermediate_G", "gas_order"}:
        raise ValueError("Select one or both supported observables")
    for kind, experiment in experiments.items():
        coarse, fine = [finite_number(experiment[k], k, positive=True) for k in ("coarse", "fine")]
        if not fine < coarse:
            raise ValueError("Fine step must be smaller than coarse step")
        selected = dict(kind=kind, species_id=experiment["species_id"])
        if kind == "gas_order":
            if experiment.get("constraint") not in (FIXED_OTHERS, FIXED_TOTAL):
                raise ValueError("Explicit gas feed constraint required")
            selected["constraint"] = experiment["constraint"]
        for label, step in (("coarse", coarse), ("fine", fine)):
            yield kind + "-" + label, dict(selected, step=step)
