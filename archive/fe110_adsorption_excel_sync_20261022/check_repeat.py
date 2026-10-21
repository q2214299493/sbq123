"""Exercise the canonical non-mutating repeat guard in the project runtime."""
from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.registry_excel_promotion import build_plan

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/adsorption_table_sync_20261022_v1"
request = Path(load_json_object(OUT / "sync_manifest.json")["accepted"][0]["request"])
try:
    build_plan(request, ROOT / "data/project_registry.sqlite3")
except ValueError as error:
    if "already promoted" not in str(error) and not str(error).startswith("receipt already exists:"):
        raise
    write_json_exclusive(OUT / "repeat_publication_check.json", {
        "blocked": True, "reason": str(error), "request_sha256": sha256_file(request), "registry_mutated": False,
    })
    print("REPEAT_PUBLICATION_BLOCKED")
else:
    raise ValueError("repeat publication should be rejected")
