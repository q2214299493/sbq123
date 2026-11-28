"""Capability-specific optional import failures; never selects a weaker backend."""
from importlib import import_module

EXTRAS = {"ase": "geometry", "sella": "sella", "pymatgen": "vasp",
          "matplotlib": "visualization", "sentence_transformers": "retrieval", "scipy": "numerics",
          "astropy": "units"}


def require_optional(module: str, capability: str):
    try:
        return import_module(module)
    except ImportError as error:
        extra = EXTRAS[module.split(".")[0]]
        raise RuntimeError(
            f"CAPABILITY_UNAVAILABLE: {capability} requires {module}; "
            f"install sbq123-common[{extra}] in a supported environment"
        ) from error
