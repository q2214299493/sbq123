from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CALC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.aqcat25_handoff import atom_order_sha256, sha256_file, validate_handoff  # noqa: E402
from scripts.neb_agent.utils_structure import read_poscar  # noqa: E402
from scripts.ts_strategy_engine.contract import load_contract  # noqa: E402


CHECKPOINT_SHA256 = "e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50"


def structure_ref(path: Path) -> dict[str, object]:
    structure = read_poscar(path)
    relative = path.resolve().relative_to(CALC_ROOT.resolve()).as_posix()
    return {
        "path": relative,
        "sha256": sha256_file(path),
        "format": "vasp_poscar",
        "atom_count": structure.atom_count,
        "atom_order_sha256": atom_order_sha256(structure.labels),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the hash-bound AQCat25 TS handoff for Topic-1 CO dissociation.")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--checkpoint-sha256", default=CHECKPOINT_SHA256)
    parser.add_argument("--round-index", type=int, default=0)
    args = parser.parse_args()
    if len(args.checkpoint_sha256) != 64 or any(value not in "0123456789abcdef" for value in args.checkpoint_sha256):
        raise ValueError("--checkpoint-sha256 must be a lowercase SHA-256 digest")
    if args.round_index < 0:
        raise ValueError("--round-index must be non-negative")

    contract = load_contract(CALC_ROOT / "contract" / "reaction.yaml")
    strategy = CALC_ROOT / "path" / "strategy_v3" / "ts_strategy.json"
    initial = CALC_ROOT / "matched_statics" / "IS" / "POSCAR"
    final = CALC_ROOT / "matched_statics" / "FS" / "POSCAR"
    waypoints = [CALC_ROOT / "gpu_handoff" / "waypoints" / f"WP_{index:02d}" / "POSCAR" for index in range(1, 4)]
    candidate = waypoints[1]
    candidate_structure = read_poscar(candidate)
    fixed = [
        index
        for index, flags in enumerate(candidate_structure.flags, start=1)
        if tuple(value.upper() for value in flags) == ("F", "F", "F")
    ]
    payload = {
        "schema_version": 2,
        "direction": "work_to_gpu",
        "handoff_id": f"fe110_co_dissociation_topic1_aqcat25_round_{args.round_index:03d}",
        "workflow_kind": "transition_state",
        "source_workflow_sha256": sha256_file(strategy),
        "candidate_structure": structure_ref(candidate),
        "compatibility": {
            "branch": "true_fe110_5layer_5x5x1",
            "sha256": contract["compatibility_sha256"],
            "slab_model": "Fe45_bottom18_fixed",
            "facet": "Fe(110)",
        },
        "model": {
            "identifier": "AQCat25 demo_single model.pt",
            "checkpoint_sha256": args.checkpoint_sha256,
            "fmax_eV_per_A": 0.05,
            "max_steps": 300,
        },
        "selective_dynamics": {
            "fixed_atom_indices_1based": fixed,
            "free_atom_count": candidate_structure.atom_count - len(fixed),
        },
        "transition_state": {
            "normalized_reaction_contract_sha256": contract["contract_sha256"],
            "atom_map_sha256": contract["atom_map_sha256"],
            "initial_structure": structure_ref(initial),
            "waypoint_structures": [structure_ref(path) for path in waypoints],
            "final_structure": structure_ref(final),
            "indexed_bond_changes": [{"atoms_1based": [46, 47], "change": "break"}],
        },
        "restrictions": {
            "predicted_candidate_only": True,
            "submit_vasp": False,
            "scientific_acceptance": False,
            "direct_gpu_to_vasp_handoff": False,
        },
    }
    encoded = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    target = CALC_ROOT / "gpu_handoff" / "handoff.json"
    if not args.write:
        print(encoded, end="")
        print("DRY_RUN", file=sys.stderr)
        return
    target.write_text(encoded, encoding="utf-8")
    validate_handoff(target, root=CALC_ROOT)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    print(f"{target}\nsha256={digest}\nVALID")


if __name__ == "__main__":
    main()
