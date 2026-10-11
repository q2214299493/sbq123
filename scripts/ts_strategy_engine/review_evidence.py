"""Host-owned, hash-bound evidence-ID tools. No model-supplied paths or commands."""
from __future__ import annotations

import json
from pathlib import Path
import stat

from scripts.artifact_io import load_json_object, sha256_file
from scripts.neb_agent.utils_structure import compatible, read_poscar
from .learning_evidence import exact_keys


TOOLS = {"inspect_interpolation": "interpolation_strategy", "inspect_image_allocation": "initial_images"}
LIMIT = 1024 * 1024


def _no_links(path: Path, *, missing_ok: bool = False):
    for component in (path, *path.parents):
        try:
            info = component.lstat()
        except FileNotFoundError:
            if missing_ok:
                continue
            raise
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError("symlink/reparse evidence path forbidden")


def safe_file(path: Path, root: Path) -> Path:
    """Reject lexical/resolved escapes, symlinks and Windows reparse points."""
    path, root = path.absolute(), root.absolute()
    if ".." in path.parts or not path.is_relative_to(root):
        raise ValueError("evidence path outside frozen material root")
    _no_links(path)
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root.resolve(strict=True)) or not resolved.is_file() \
            or resolved.stat().st_size > LIMIT:
        raise ValueError("invalid or oversized evidence file")
    return resolved


def new_output(path: Path, forbidden: list[Path]) -> Path:
    _no_links(path.absolute(), missing_ok=True)
    resolved = path.resolve()
    if ".." in path.parts or any(resolved.is_relative_to(root.resolve()) for root in forbidden):
        raise ValueError("review output must be outside frozen trial and policy store")
    resolved.mkdir(parents=True, exist_ok=False)
    return resolved


class EvidenceTools:
    def __init__(self, materials: dict, root: Path):
        if not isinstance(materials, dict) or not materials:
            raise ValueError("frozen evidence-ID manifest required")
        self.materials, self.root = materials, root
        for identity in materials:
            if not isinstance(identity, str) or not identity or "/" in identity or "\\" in identity:
                raise ValueError("evidence ID is not a path")
            self.path(identity)

    def path(self, identity: str) -> Path:
        if identity not in self.materials:
            raise ValueError("unlisted evidence ID")
        reference = self.materials[identity]
        path = safe_file(Path(reference["path"]), self.root)
        if sha256_file(path) != reference["sha256"]:
            raise ValueError("stale evidence hash")
        return path

    def specs(self) -> list:
        return [{"type": "function", "name": name,
                 "description": f"Read frozen evidence and deterministic structure identity checks for {field}. No scientific acceptance.",
                 "inputSchema": {"type": "object", "properties": {"evidence_ids": {
                     "type": "array", "items": {"type": "string", "enum": sorted(self.materials)},
                     "minItems": 1, "maxItems": len(self.materials), "uniqueItems": True}},
                     "required": ["evidence_ids"], "additionalProperties": False}}
                for name, field in TOOLS.items()]

    def execute(self, tool: str, arguments: dict) -> dict:
        if tool not in TOOLS:
            raise ValueError("unapproved tool")
        exact_keys(arguments, {"evidence_ids"})
        identities = arguments["evidence_ids"]
        if not isinstance(identities, list) or not identities or len(identities) > len(self.materials) \
                or any(not isinstance(item, str) for item in identities) or len(set(identities)) != len(identities):
            raise ValueError("unique listed evidence IDs required")
        evidence, structures = [], []
        total = 0
        for identity in identities:
            path = self.path(identity)
            total += path.stat().st_size
            if total > LIMIT:
                raise ValueError("tool evidence exceeds 1 MiB")
            if identity.startswith(("input_image_", "chemical_waypoint_")):
                structure = read_poscar(path)
                structures.append((identity, structure))
                parsed = {"atom_count": structure.atom_count, "atom_order": structure.labels,
                          "cell_angstrom": structure.cell.tolist(), "fractional_coordinates": structure.frac.tolist(),
                          "selective": structure.selective, "flags": structure.flags}
            elif path.suffix.lower() == ".json":
                parsed = load_json_object(path)
            else:
                parsed = {"saved_text": path.read_text(encoding="utf-8")}
            self.path(identity)  # Reject a changed source even if its parser returned successfully.
            evidence.append({"evidence_id": identity, "sha256": self.materials[identity]["sha256"], "parsed": parsed})
        errors = {name: compatible(structures[0][1], structure) for name, structure in structures[1:]}
        documents = {e["evidence_id"]: e["parsed"] for e in evidence}
        seed, contract = documents.get("seed_generation", {}), documents.get("contract", {})
        if tool == "inspect_interpolation":
            focused = {"saved_method": seed.get("method_used"), "saved_waypoint_sources": seed.get("waypoint_sources"),
                       "saved_periodic_branch": seed.get("periodic_branch"), "atom_map": contract.get("atom_map"),
                       "site_changes": contract.get("site_changes"),
                       "parsed_waypoint_ids": [name for name, _ in structures if name.startswith("chemical_waypoint_")]}
        else:
            focused = {"saved_internal_images": seed.get("interior_images"),
                       "saved_image_directories": seed.get("image_directories"),
                       "saved_segment_allocation": seed.get("segment_additional_images"),
                       "parsed_image_ids": [name for name, _ in structures if name.startswith("input_image_")],
                       "saved_coverage_by_source": {name: document.get("geometry_guards") for name, document in documents.items()
                                                    if name in {"seed_snapshot", "geometry_failure"}}}
        # These are observations, not path approval. Threshold/chemistry decisions stay with their owner.
        return {"field": TOOLS[tool], "field_evidence": focused, "evidence": evidence, "structure_identity_errors": errors,
                "scientific_judgment": None, "execution_permission": False,
                "all_manifest_sources_read": set(identities) == self.materials.keys()}

    @staticmethod
    def response(result: dict, success: bool) -> dict:
        return {"contentItems": [{"type": "inputText", "text": json.dumps(result, ensure_ascii=False)}],
                "success": success}
