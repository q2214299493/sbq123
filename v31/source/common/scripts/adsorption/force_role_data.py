"""Validated metadata for opt-in adsorption role objectives; no training authority."""
import numpy as np

ROLE_NAMES = ("adsorbate_C", "adsorbate_O", "adsorbate_H", "near_Fe", "other_Fe")
ROLE_IDS = {name: i + 1 for i, name in enumerate(ROLE_NAMES)}  # zero is fixed
DATA_KEYS = ("adsorption_force_weights", "adsorption_force_roles", "adsorption_replay")
TRAINER = "scripts.adsorption.role_force_trainer.RoleForceTrainer"


def role_metadata(row: dict, split: str) -> dict:
    count = len(row["symbols"])
    fixed = set(row["fixed_atom_indices_0based"])
    groups = row["force_role_groups"]
    if set(groups) != set(ROLE_NAMES):
        raise ValueError("unexpected force role groups")
    roles = np.zeros(count, dtype=np.int64)
    seen = set()
    for name, indices in groups.items():
        for i in indices:
            if not isinstance(i, int) or i < 0 or i >= count or i in fixed or i in seen:
                raise ValueError("invalid/overlapping force role atom")
            expected = name.removeprefix("adsorbate_") if name.startswith("adsorbate_") else "Fe"
            if row["symbols"][i] != expected:
                raise ValueError("force role element mismatch")
            roles[i] = ROLE_IDS[name]
            seen.add(i)
    if seen != set(range(count)) - fixed:
        raise ValueError("roles do not partition free atoms")
    weights = np.asarray(row["proposed_per_atom_loss_weights"], dtype=float)
    if weights.shape != (count,) or not np.isfinite(weights).all() or (weights < 0).any():
        raise ValueError("invalid per-atom role weights")
    if np.any(weights[list(fixed)] != 0) or np.any(weights[list(seen)] <= 0) or not np.isclose(weights.sum(), 1., rtol=0, atol=1e-12):
        raise ValueError("role weights must exclude fixed atoms and sum to one")
    replay = row.get("stage") == "replay" or "retention" in row.get("sample_role", "")
    data = {DATA_KEYS[0]: weights.tolist(), DATA_KEYS[1]: roles.tolist(), DATA_KEYS[2]: int(replay)}
    if split == "train":
        probability = row["proposed_source_stage_sampling_probability"]
        if not np.isfinite(probability) or probability <= 0:
            raise ValueError("invalid training sampling probability")
        data["adsorption_sampling_probability"] = float(probability)
    return data


def sampling_probabilities(rows) -> np.ndarray | None:
    present = ["adsorption_sampling_probability" in row.data for row in rows]
    if not any(present):
        return None
    if not all(present):
        raise ValueError("mixed role-sampling metadata")
    values = np.asarray([row.data.adsorption_sampling_probability for row in rows], dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any() or not np.isclose(values.sum(), 1., rtol=0, atol=1e-12):
        raise ValueError("invalid role-sampling distribution")
    return values


def validate_role_contract(request: dict, config: dict) -> None:
    if request.get("runtime_contract_version", 1) < 3:
        raise ValueError("role-weighted manifest requires runtime contract v3")
    if config.get("trainer") != TRAINER:
        raise ValueError("role objective requires explicit RoleForceTrainer")
    if config["optim"].get("grouped_force_objective") is not True:
        raise ValueError("grouped force objective not enabled")
    for key in ("train", "val"):
        if not set(DATA_KEYS) <= set(config["dataset"][key]["a2g_args"]["r_data_keys"]):
            raise ValueError("role tensors are not passed into graph conversion")
    if config["evaluation_metrics"]["primary_metric"] != "forces_role_vector_mae":
        raise ValueError("role-aware development selection metric missing")
    paths = {item["path"] for item in request.get("artifacts", [])}
    required = {"runtime/scripts/adsorption/" + name + ".py" for name in
                ("force_role_data", "force_role_runtime", "role_force_trainer")}
    if not required <= paths:
        raise ValueError("role runtime sources are not hash bound")

