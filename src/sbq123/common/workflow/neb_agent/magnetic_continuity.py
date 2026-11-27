from __future__ import annotations

from typing import Any


def evaluate_magnetic_continuity(
    images: list[dict[str, Any]],
    warning_threshold_muB: float,
) -> dict[str, Any]:
    warnings = []
    for left, right in zip(images, images[1:]):
        left_value = left.get("final_total_magnetization_muB")
        right_value = right.get("final_total_magnetization_muB")
        if left_value is None or right_value is None:
            continue
        delta = abs(float(right_value) - float(left_value))
        if delta > warning_threshold_muB:
            warnings.append(
                {
                    "left": str(left["image"]),
                    "right": str(right["image"]),
                    "delta_muB": delta,
                }
            )
    return {
        "rule": "MAGNETIC_CONTINUITY_RULE",
        "severity": "SOFT_WARNING",
        "warning_threshold_muB": warning_threshold_muB,
        "warnings": warnings,
        "action": "CHECK_MAGNETIC_STATE_CONTINUITY",
        "stops_current_job": False,
        "blocks_ordinary_no_climb_neb": False,
        "proves_magnetic_state_switch": False,
    }
