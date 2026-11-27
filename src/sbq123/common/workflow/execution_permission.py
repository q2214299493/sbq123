"""Check a module-validated decision against the current execution state and action vocabulary."""

from scripts.artifact_io import require_sha256


def require_bound_action(decision, action, current_state_sha256, known_actions):
    require_sha256(current_state_sha256, label="current execution state")
    if decision.get("state_sha256") != current_state_sha256:
        raise ValueError("execution decision is stale for the current calculation state")
    if action not in known_actions:
        raise ValueError(f"unknown execution action: {action}")
    if action not in decision.get("ALLOWED_ACTIONS", []):
        raise PermissionError(f"{action} is not authorized by {decision.get('DECISION')}")
    return decision
