"""Public scientific registry selectors."""
from ._records import entry as entry
from sbq123.common.kinetic_model.contracts import Model
from sbq123.common.kinetic_model.archive import read_registered_cycle


def dataset(key: str) -> Model:
    """Resolve a kinetic model from the installed release authority."""
    if key == "v31-closed-cycle":
        return read_registered_cycle()
    row = entry("datasets", key)
    return Model._from_verified_record(row["model"], registered_digest=row["sha256"], provenance=row["scope"])
