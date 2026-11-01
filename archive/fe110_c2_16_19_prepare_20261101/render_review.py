"""Render verified coordinates with explicit view labels and uncropped atoms."""
import json
from pathlib import Path
import zipfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from scripts.artifact_io import sha256_file, write_json_exclusive
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_batch import display_coordinates, draw_pose
from .prepare import OUT, SLAB, TASK


def main():
    verification = json.loads((OUT / "independent_verification.json").read_text(encoding="utf-8"))
    assert verification["status"] == "PASS_GEOMETRY_READBACK_ONLY"
    assert sha256_file(OUT / "candidate_review.json") == verification["manifest_sha256"]
    slab = read_poscar(SLAB)
    images = []
    for number in ("16", "17", "18", "19"):
        target = OUT / (number + "_review.png")
        if target.exists():
            raise FileExistsError("Preserve prior review images")
        fig, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
        for column, label in enumerate("ABC"):
            name = number + "_" + label
            pose = read_poscar(OUT / name / "POSCAR")
            draw_pose(axes[:, column], pose, slab, name)
            xy = display_coordinates(pose)[45:, :2]
            axes[0, column].set_xlim(min(-3.5, xy[:, 0].min() - .45), max(3.5, xy[:, 0].max() + .45))
            axes[0, column].set_ylim(min(-3.5, xy[:, 1].min() - .45), max(3.5, xy[:, 1].max() + .45))
            axes[0, column].set_title(name + " | TOP VIEW (not a site label)")
            axes[1, column].set_title(name + " | SIDE VIEW")
            for ax in axes[:, column]:
                for text in list(ax.texts):
                    if text.get_text().startswith("H"):
                        text.remove()
        fig.suptitle(number + " | Fe(110), Fe45, bottom18 Fe fixed\nExploratory starting geometries: NOT optimized, NOT stability-ranked. Fe gray / C black / O red / H blue.")
        fig.savefig(target, dpi=145)
        plt.close(fig)
        images.append(target)
    archive = TASK / "Fe110_16_19_review_bundle.zip"
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as bundle:
        for number in ("16", "17", "18", "19"):
            for label in "ABC":
                path = OUT / (number + "_" + label) / "POSCAR"
                bundle.write(path, path.relative_to(OUT).as_posix())
        for path in images + [OUT / "candidate_review.json", OUT / "independent_verification.json", OUT / "structure_review.md"]:
            bundle.write(path, path.name)
        for name in ("request.json", "image_query.json", "whitelist_screen.json", "literature_screening.json", "preparation_failures.json"):
            bundle.write(TASK / name, "evidence/" + name)
    write_json_exclusive(OUT / "review_bundle_receipt.json", {
        "archive": str(archive), "sha256": sha256_file(archive), "coordinate_manifest_sha256": verification["manifest_sha256"],
        "images": [{"path": str(path), "sha256": sha256_file(path)} for path in images],
        "coordinate_changes": False, "scientific_acceptance": False,
    })
    print(json.dumps({"archive": str(archive), "images": len(images), "coordinate_changes": False}))


if __name__ == "__main__":
    main()
