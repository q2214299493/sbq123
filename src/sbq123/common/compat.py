"""Explicit, process-local compatibility for the historical scripts imports."""

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
from importlib.resources import files
import json
from pathlib import Path
import sys
from threading import RLock

_lock = RLock()
_active = None


class _CanonicalAlias(importlib.machinery.SourceFileLoader):
    def __init__(self, name, path, target):
        super().__init__(name, str(path))
        self.target = target

    def exec_module(self, module):
        sys.modules[module.__name__] = importlib.import_module(self.target)


class RoleImports(importlib.abc.MetaPathFinder):
    def __init__(self, role):
        self.role = role
        self.paths = {}
        for owner in ("common", role):
            root = files("sbq123." + owner)
            table = json.loads(root.joinpath("_legacy_modules.json").read_bytes())
            for module, (relative, package) in table.items():
                if module in self.paths:
                    raise ImportError(f"Duplicate owner of {module}")
                self.paths[module] = (Path(str(root)).parent / relative, package)

    def find_spec(self, fullname, path=None, target=None):
        row = self.paths.get(fullname)
        if row is None and any(n.startswith(fullname + ".") for n in self.paths):
            return importlib.machinery.ModuleSpec(fullname, None, is_package=True)
        if row is None:
            if fullname.startswith("scripts."):
                raise ModuleNotFoundError(f"{fullname} is outside the {self.role} inventory")
            return None
        filename, package = row
        if not package and not fullname.endswith(".__main__"):
            parts = filename.parts
            package_index = len(parts) - 1 - parts[::-1].index("sbq123")
            target = ".".join((*parts[package_index:-1], filename.stem))
            if (target.startswith(("sbq123.analysis.", "sbq123.discovery.", "sbq123.common."))
                    and not target.startswith("sbq123.common.workflow.") or target == "sbq123.common.workflow.runtime_resources"):
                return importlib.util.spec_from_file_location(fullname, filename, loader=_CanonicalAlias(fullname, filename, target))
        return importlib.util.spec_from_file_location(fullname, filename, submodule_search_locations=[] if package else None)


def activate(role, *, _package=None):
    global _active
    if role not in ("mkm", "kmc"):
        raise ValueError("Expected mkm or kmc")
    with _lock:
        if _active is None:
            finder = RoleImports(role)
            if any(n in sys.modules and not (n == "scripts" and _package is sys.modules[n]) for n in finder.paths):
                raise ImportError("Historical modules are already loaded from another context")
            sys.meta_path.insert(0, finder)
            _active = finder
        elif _active.role != role:
            raise ValueError("Use a separate interpreter for each role")
        return _active


def historical_module(role, name):
    activate(role)
    return importlib.import_module(name)
