"""Public scientific registry selectors."""
from ._records import entry as entry
from sbq123.common.kinetic_model.contracts import Model
from sbq123.common.kinetic_model.archive import read_registered_cycle


def dataset(key: str) -> Model:
    """Resolve a kinetic model from the installed release authority."""
    if key == "v31-closed-cycle":
        return read_registered_cycle()
    row = model_record(key)
    return Model._from_verified_record(row["model"], registered_digest=row["sha256"], provenance=row["scope"])


def model_record(key):
    from ._records import _registry
    from sbq123.common.kinetic_model.contracts import identity
    from .trust import project_document, project_records
    if key in _registry("datasets") or key in project_records("datasets"):
        return entry("datasets", key)
    binding = project_document("network_model", key)
    if binding is not None:
        from sbq123.common.kinetic_model.archive import network_record
        ref, _ = binding
        if ref["scope"] != "reviewed_project" or ref["use_scope"] != "project":
            raise ValueError("Project kinetic model requires reviewed project scope")
        docs = []
        for kind in ("network", "kinetic_dataset"):
            doc = project_document(kind, ref[kind]["id"])
            if doc is None or doc[1] != ref[kind]["sha256"]:
                raise ValueError("Network conversion source has changed")
            docs.append(doc[0])
        raw = network_record(*docs, scope=ref["use_scope"])
        return dict(model=raw, sha256=identity(raw), scope=ref["scope"])
    raise ValueError("Unknown kinetic dataset")
