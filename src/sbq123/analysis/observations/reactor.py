"""Understand a reactor result using an identity retained separately by its producer."""

from sbq123.common.kinetic_model.contracts import identity


def reactor_observation(result, expected_sha256):
    data = {k: v for k, v in result.items() if k != "result_sha256"}
    if identity(data) != expected_sha256 or result.get("result_sha256") != expected_sha256:
        raise ValueError("Reactor result differs from the retained receipt")
    if (
        data.get("schema_version") not in (1, 2)
        or data.get("kinetic_mode") not in ("fixed", "dynamic_mkm")
        or data.get("model") not in ("Batch", "CSTR", "PFR")
        or not data.get("points")
    ):
        raise ValueError("Invalid reactor result")
    if data["schema_version"] == 2 and (
        data["model"] not in ("PFR", "CSTR")
        or data.get("cantera_version") != "3.2.0"
        or len(data.get("mechanism_sha256", "")) != 64
        or not data.get("solver", {}).get("success")
    ):
        raise ValueError("Invalid Cantera result contract")
    return {
        "result_sha256": expected_sha256,
        "dataset_sha256": data["model_sha256"],
        "reactor": data["model"],
        "kinetic_mode": data["kinetic_mode"],
        "scope": data["scope"],
        "coordinate_unit": data["coordinate_unit"],
        "denominators": dict(data["denominators"]),
        "conversion": [float(r["conversion"]) for r in data["points"]],
        "uncertainty": data["uncertainty"],
        "roots_found": data["solver"].get("roots_found"),
    }


def interpret(result, expected_sha256):
    obs = reactor_observation(result, expected_sha256)
    return {
        "observation": obs,
        "description": f"{obs['reactor']} conversion in the {obs['scope']} scope using {obs['kinetic_mode']} kinetics.",
        "scientific_promotion": False,
    }
