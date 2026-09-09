from __future__ import annotations

import argparse
import json
from pathlib import Path



from scripts.registry_mutations import (
    DEFAULT_DATABASE, apply_registry_batch, load_registry_batch, plan_registry_batch,
    validate_registry_batch,
)

__all__ = ["apply_registry_batch", "load_registry_batch", "plan_registry_batch", "validate_registry_batch"]

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plan or apply a schema-gated append-only calculation-registry batch."
    )
    parser.add_argument("command", choices=("plan", "apply"))
    parser.add_argument("--db", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--confirm-sha256")
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    batch = load_registry_batch(args.manifest)
    if args.command == "plan":
        result = plan_registry_batch(args.db, batch)
    else:
        if not args.confirm_sha256 or not args.plan or not args.approval:
            raise ValueError("apply requires --plan, --approval and --confirm-sha256 from a reviewed plan")
        result = apply_registry_batch(
            args.db,
            batch,
            confirmed_sha256=args.confirm_sha256,
            plan=json.loads(args.plan.read_text(encoding="utf-8")),
            approval=json.loads(args.approval.read_text(encoding="utf-8")),
        )
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "batch_id": result["batch_id"],
                    "batch_sha256": result["batch_sha256"],
                    "insert_count": result.get("insert_count", result.get("inserted", 0)),
                    "update_count": result.get("update_count", result.get("updated", 0)),
                    "unchanged_count": result.get("unchanged_count", result.get("unchanged", 0)),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
