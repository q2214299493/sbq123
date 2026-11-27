"""Pure compatible final-energy barrier values; no registry or execution authority."""
from scripts.scientific_validation import finite_number


ACCEPTED_STATIC_STATUS = "accepted_matched_static"
ACCEPTED_COMPATIBLE_FINAL_ENERGY_STATUS = "accepted_compatible_final_energy"
ACCEPTED_FINAL_ENERGY_STATUSES = frozenset(
    {ACCEPTED_STATIC_STATUS, ACCEPTED_COMPATIBLE_FINAL_ENERGY_STATUS}
)


def validate_barrier_values(values: dict) -> dict[str, float]:
    """Validate calculated or stored barriers before scientific reuse/export."""
    values = {key: finite_number(values[key], key) for key in (
        "forward_barrier_ev", "reverse_barrier_ev", "reaction_energy_ev",
    )}
    if values["forward_barrier_ev"] < 0 or values["reverse_barrier_ev"] < 0:
        raise ValueError("TS final energy lies below an endpoint")
    return values
