"""ML prediction records retain model/input identity and explicit uncertainty.

No function here accepts a scientific result or writes a registry. Unknown
uncertainty is explicit and keeps a prediction restricted to candidate guidance.
"""
from __future__ import annotations

import hashlib

from scripts.provenance_fields import required_text, timestamp
from scripts.scientific_validation import finite_number, validate_finite_tree


def validate_prediction(record: dict) -> dict:
    if record.get("type") != "model_prediction":
        raise ValueError("prediction provenance cannot become scientific_fact")
    for field in ("model_name", "model_version", "input_fingerprint", "source_reference", "evidence_relationship"):
        required_text(record.get(field), f"prediction.{field}")
    timestamp(record.get("generated_at"), "prediction.generated_at")
    uncertainty = record.get("uncertainty")
    if not isinstance(uncertainty, dict):
        raise ValueError("prediction uncertainty is required")
    if uncertainty.get("status") == "estimated":
        finite_number(uncertainty.get("value"), "prediction uncertainty", nonnegative=True)
        required_text(uncertainty.get("method"), "uncertainty method")
        required_text(uncertainty.get("unit"), "uncertainty unit")
    elif uncertainty.get("status") == "unavailable":
        required_text(uncertainty.get("reason"), "unavailable uncertainty reason")
        if uncertainty.get("value") is not None:
            raise ValueError("unavailable uncertainty cannot carry a numeric estimate")
    else:
        raise ValueError("invalid uncertainty status")
    if record.get("status") != "predicted_candidate" or record.get("scientific_acceptance") is not False:
        raise ValueError("prediction cannot self-authorize scientific acceptance")
    if "training_split" not in record:
        raise ValueError("training split metadata must be explicit (null if unavailable)")
    validate_finite_tree(record)
    return record


def model_state_identity(model) -> str:
    """Identify the actual in-memory weights, including unsaved training updates."""
    import torch

    digest = hashlib.sha256()
    for key, value in sorted(model.state_dict().items()):
        tensor = value.detach().cpu().contiguous()
        digest.update(f"{key}:{tensor.dtype}:{tuple(tensor.shape)}:".encode())
        digest.update(tensor.reshape(-1).view(torch.uint8).numpy().tobytes())
    return digest.hexdigest()


def prediction_metadata(*, model_name, model_version, input_fingerprint, source_reference,
                        generated_at, uncertainty, training_split=None) -> dict:
    return validate_prediction({
        "type": "model_prediction", "model_name": model_name, "model_version": model_version,
        "input_fingerprint": input_fingerprint, "source_reference": source_reference,
        "generated_at": generated_at, "uncertainty": uncertainty, "training_split": training_split,
        "status": "predicted_candidate", "evidence_relationship": "prediction_from_model",
        "scientific_acceptance": False,
    })
