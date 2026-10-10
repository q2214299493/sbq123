"""Performance accounting only; cannot authorize calculations or accept chemistry."""

import math


def _number(value, label, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("invalid " + label)
    if (positive and value <= 0) or (not positive and value < 0):
        raise ValueError("invalid " + label)
    return float(value)


def compare_costs(baseline, accelerated, gpu_seconds, shared_training_and_label_seconds=0, amortization_tasks=1):
    """Compare compatible, already reviewed runs; queue waiting excluded.

    Run observations are inputs from the owning scientific review, not evidence
    created or accepted by this function. Shared costs are reported both fully
    charged and amortized; this is elapsed-resource accounting, not parallel
    calendar makespan or an equivalence between GPU-hours and CPU-core-hours.
    """
    required = ("normal_completion", "electronic_converged", "force_converged", "geometry_accepted")
    for run in (baseline, accelerated):
        if any(run.get(key) is not True for key in required):
            raise ValueError("performance comparison requires completed scientifically reviewed runs")
    for key in ("original_seed_sha256", "compatibility_sha256", "resource_signature", "reviewed_minimum_id"):
        if not baseline.get(key) or baseline[key] != accelerated.get(key):
            raise ValueError("unmatched comparison: " + key)
    direct = _number(baseline["vasp_elapsed_seconds"], "baseline runtime", True)
    corrected = _number(accelerated["vasp_elapsed_seconds"], "accelerated runtime", True)
    base_steps = _number(baseline["ionic_steps"], "baseline steps", True)
    new_steps = _number(accelerated["ionic_steps"], "accelerated steps", True)
    gpu = _number(gpu_seconds, "GPU cost")
    shared = _number(shared_training_and_label_seconds, "training and labeling cost")
    if isinstance(amortization_tasks, bool) or not isinstance(amortization_tasks, int) or amortization_tasks < 1:
        raise ValueError("amortization_tasks must be a declared positive integer")
    recurring = corrected + gpu
    first = recurring + shared
    amortized = recurring + shared / amortization_tasks
    savings = direct - recurring
    return {
        "vasp_step_ratio": base_steps / new_steps,
        "vasp_runtime_ratio": direct / corrected,
        "first_case_total_runtime_ratio": direct / first,
        "amortized_runtime_ratio": direct / amortized,
        "amortization_tasks": amortization_tasks,
        "recurring_seconds_saved": savings,
        "cases_until_shared_cost_recovered": math.ceil(shared / savings) if savings > 0 else None,
        "first_case_cost_reduced": first < direct,
        "amortized_cost_reduced": amortized < direct,
        "submit_authority": False,
        "scientific_acceptance_authority": False,
    }
