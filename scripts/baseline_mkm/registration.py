"""Prepare deterministic registry rows for one validated MKM run; registry-write owns mutations."""

import argparse
from pathlib import Path

from scripts.artifact_io import load_json_object as read, sha256_file, sha256_json, write_json_exclusive
from scripts.baseline_mkm.single_point import status
from scripts.registry_write import validate_registry_batch


def registry_batch(run, reviewer):
    run = run.resolve()
    view = status(run)
    if view["stage"] != "ACCEPTED":
        raise ValueError("Only a validated point can produce result rows")
    plan = read(run / "plan.json")
    result = read(run / "result.json")
    key = "mkm-" + sha256_json(plan)
    if result["plan_sha256"] != sha256_json(plan) or result["output_hashes"] != view["output_hashes"]:
        raise ValueError("Result provenance differs from accepted run")
    hashes = dict(result["output_hashes"], **{k + ".json": v for k, v in plan["input_hashes"].items()})
    hashes.update({"input/" + k: v for k, v in plan["native_input_hashes"].items()})
    hashes.update(
        {
            "result.json": view["result_sha256"],
            "approval.json": sha256_file(run / "approval.json"),
            "plan.json": sha256_file(run / "plan.json"),
            "ACCEPTED.json": sha256_file(run / "ACCEPTED.json"),
        }
    )
    if sha256_json(read(run / "approval.json")) != view["approval_reference"]:
        raise ValueError("Approval reference has changed")
    files = []
    for name, digest in hashes.items():
        path = run / name
        if sha256_file(path) != digest:
            raise ValueError(f"Changed registered artifact: {name}")
        files.append(
            dict(
                file_id=key + "-" + name.replace("/", "-"),
                calculation_id=key,
                role="mkm_artifact",
                filename=path.name,
                local_path=str(path),
                storage_mode="local",
                existence_status="confirmed",
                sha256=digest,
            )
        )
    stamp = view["timestamp"]
    rows = []
    quantities = [("steady_state_residual", result["steady_state_residual"], result["flux_unit"])]
    if result["tof_s_inverse"] is not None:
        quantities.append(("tof_s_inverse", result["tof_s_inverse"], "s^-1"))
    for name, value, unit in quantities:
        rows.append(
            dict(
                result_id=key + "-" + name,
                calculation_id=key,
                result_name=name,
                numeric_value=value,
                unit=unit,
                temperature_k=plan["temperature_K"],
                pressure_pa=plan["total_pressure_bar"] * 1e5,
                reference_convention=result["flux_unit"],
                source_file_id=key + "-result.json",
                source_locator="/" + name,
                extraction_method="CATKINAS single point with independent mass-action validation",
                validation_status="validated_within_scope",
                created_at=stamp,
                notes=plan["use_scope"],
            )
        )
    provenance = {}
    for row in rows:
        claim = dict(
            id=row["result_id"],
            type="calculated_result",
            statement=f"{row['result_name']} = {row['numeric_value']} {row['unit']}",
            source_reference=view["result_sha256"],
            status="validated_within_scope",
            scope=plan["use_scope"],
            domain="baseline_mkm",
            evidence_relationship="normalized CATKINAS result",
            result_sha256=sha256_json(row),
        )
        provenance[row["result_id"]] = dict(
            type="calculated_result", registry_stage="candidate", evidence={"claim": claim}
        )
    return validate_registry_batch(
        dict(
            schema_version=1,
            result_provenance=provenance,
            document_kind="calculation_registry_batch",
            batch_id=key,
            reviewer=reviewer,
            reason="Register validated point within " + plan["use_scope"],
            created_at=stamp,
            rows={
                "calculations": [
                    dict(
                        calculation_id=key,
                        module="baseline_mkm",
                        purpose=plan["use_scope"],
                        workflow_status="registered",
                        created_at=stamp,
                    )
                ],
                "files": files,
                "results": rows,
            },
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("run", type=Path)
    p.add_argument("reviewer")
    p.add_argument("output", type=Path)
    args = p.parse_args()
    write_json_exclusive(args.output, registry_batch(args.run, args.reviewer))
