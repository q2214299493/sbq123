from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .adsmind_common import write_json


def export_selected(
    records: list[dict[str, Any]],
    output_root: Path,
    include_medium: bool = True,
    include_low: bool = False,
    include_needs_review: bool = False,
) -> list[dict[str, Any]]:
    exported: list[dict[str, Any]] = []
    for record in records:
        confidence = record.get("confidence_level")
        allowed_confidence = confidence == "high" or (include_medium and confidence == "medium") or (include_low and confidence == "low")
        review_allowed = not record.get("needs_review") or include_needs_review
        explicit_override = (include_low and confidence == "low") or (include_needs_review and record.get("needs_review"))
        if (
            (not record.get("recommend_for_vasp") and not explicit_override)
            or record.get("duplicate")
            or not review_allowed
            or not allowed_confidence
        ):
            continue
        source = Path(record.get("selected_structure") or record.get("relaxed_structure") or record["initial_structure"])
        folder = output_root / str(record["surface_name"]) / str(record["adsorbate"]) / str(record["candidate_id"])
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, folder / "POSCAR")
        write_json(folder / "metadata.json", record)
        exported.append(record)
    return exported
