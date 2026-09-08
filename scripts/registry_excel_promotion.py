"""Hash-bound promotion of accepted registry records into reviewed Excel views.

The calculation registry remains the source of scientific values.  A request can
only bind numerical cells to accepted registry records; human-readable labels
are explicitly marked as reviewed metadata.  Applying a plan uses the bundled
``@oai/artifact-tool`` writer, rechecks the workbook hash, and records a
receipt in both SQLite and JSON.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.artifact_io import canonical_json, sha256_file, sha256_json, write_json_atomic
from scripts.ts_strategy_engine.registry import open_registry


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / "data" / "project_registry.sqlite3"
DEFAULT_WRITER = ROOT / "scripts" / "registry_excel_writer.mjs"
WRITER_TIMEOUT_SECONDS = 300
DEFAULT_RECEIPTS = ROOT / "data" / "registry_promotion_receipts"
PROMOTION_KINDS = {"adsorption", "barrier"}
ACCEPTED_FINAL_ENERGY_PROMOTION_STATUSES = frozenset(
    {"accepted_matched_static", "accepted_compatible_final_energy"}
)
ACCEPTED_ADSORPTION_PROMOTION_STATUSES = (
    ACCEPTED_FINAL_ENERGY_PROMOTION_STATUSES
    | {"accepted_compatible_adsorption_energy"}
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rooted_path(value: str | Path, *, label: str) -> Path:
    path = Path(value)
    resolved = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside the repository: {value}") from exc
    return resolved


def _request_path(value: str | Path) -> Path:
    path = Path(value).resolve()
    if not path.is_file():
        raise ValueError(f"promotion request not found: {path}")
    return path


def _require_text(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"promotion request requires non-empty {key}")
    return value.strip()


def load_request(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("promotion request must be a JSON object")
    if payload.get("schema_version") != 1:
        raise ValueError("promotion request schema_version must be 1")
    _require_text(payload, "promotion_id")
    kind = _require_text(payload, "promotion_kind")
    if kind not in PROMOTION_KINDS:
        raise ValueError(f"unsupported promotion_kind: {kind}")
    _require_text(payload, "registry_id")
    workbook = payload.get("workbook")
    if not isinstance(workbook, dict):
        raise ValueError("promotion request requires workbook object")
    _require_text(workbook, "path")
    _require_text(workbook, "worksheet_name")
    if not isinstance(workbook.get("header_row"), int) or workbook["header_row"] < 1:
        raise ValueError("workbook.header_row must be a positive integer")
    headers = workbook.get("headers")
    if not isinstance(headers, list) or not headers or any(not isinstance(item, str) or not item.strip() for item in headers):
        raise ValueError("workbook.headers must be a non-empty list of labels")
    if len(headers) != len(set(headers)):
        raise ValueError("workbook.headers cannot contain duplicates")
    target_row = workbook.get("target_row")
    if target_row is not None and (
        not isinstance(target_row, int) or target_row <= workbook["header_row"]
    ):
        raise ValueError("workbook.target_row must be below the header row")
    columns = payload.get("columns")
    if not isinstance(columns, list) or len(columns) != len(headers):
        raise ValueError("columns must contain exactly one binding for each workbook header")
    review = payload.get("review")
    if not isinstance(review, dict) or review.get("decision") != "approve":
        raise ValueError("promotion request requires a reviewed decision=approve")
    _require_text(review, "reviewer")
    _require_text(review, "reviewed_at")
    return payload


def _validate_unpromoted(connection: sqlite3.Connection, request: dict[str, Any]) -> None:
    row = connection.execute(
        "SELECT promotion_id FROM excel_promotions WHERE promotion_kind=? AND registry_id=?",
        (request["promotion_kind"], request["registry_id"]),
    ).fetchone()
    if row is not None:
        raise ValueError(f"registry entity is already promoted by {row[0]}")


def _result_value(
    connection: sqlite3.Connection,
    *,
    calculation_id: str,
    result_id: str,
    accepted_statuses: frozenset[str] = ACCEPTED_FINAL_ENERGY_PROMOTION_STATUSES,
) -> tuple[Any, dict[str, Any]]:
    row = connection.execute(
        """
        SELECT result_id, calculation_id, result_name, numeric_value, text_value, unit,
               validation_status, source_file_id, reference_convention
        FROM results WHERE result_id=?
        """,
        (result_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"registry result not found: {result_id}")
    item = dict(row)
    if item["calculation_id"] != calculation_id:
        raise ValueError(f"result {result_id} does not belong to calculation {calculation_id}")
    if item["validation_status"] not in accepted_statuses or not item["source_file_id"]:
        raise ValueError(f"result {result_id} is not an accepted compatible final-energy result")
    if (
        item["validation_status"] == "accepted_compatible_adsorption_energy"
        and item["result_name"] != "adsorption_energy"
    ):
        raise ValueError(
            f"result {result_id} has adsorption-energy validation on a non-adsorption result"
        )
    value = item["numeric_value"] if item["numeric_value"] is not None else item["text_value"]
    if value is None:
        raise ValueError(f"result {result_id} has no value")
    return value, item


def _reviewed_metadata(source: dict[str, Any]) -> str:
    value = source.get("value")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("reviewed_metadata must be a non-empty text value")
    return value.strip()


def _adsorption_context(connection: sqlite3.Connection, calculation_id: str) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT c.calculation_id, c.module, c.workflow_status, c.purpose, c.scientific_system,
               cc.compatibility_fingerprint
        FROM calculations AS c
        LEFT JOIN calculation_compatibility AS cc ON cc.calculation_id=c.calculation_id
        WHERE c.calculation_id=?
        """,
        (calculation_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"adsorption calculation not found: {calculation_id}")
    item = dict(row)
    if item["module"] != "adsorption_workflow":
        raise ValueError("adsorption promotion requires a calculation owned by adsorption_workflow")
    if item["workflow_status"] not in {"static_accepted", "energy_accepted"}:
        raise ValueError(
            "adsorption promotion requires workflow_status=static_accepted or energy_accepted"
        )
    if not item["compatibility_fingerprint"]:
        raise ValueError("adsorption promotion requires a registered compatibility fingerprint")
    scheduler_record = connection.execute(
        """
        SELECT 1 FROM jobs AS j JOIN job_status_history AS h ON h.job_record_id=j.job_record_id
        WHERE j.calculation_id=? LIMIT 1
        """,
        (calculation_id,),
    ).fetchone()
    if scheduler_record is None:
        raise ValueError("adsorption promotion requires a recorded scheduler status")
    return item


def _barrier_context(connection: sqlite3.Connection, barrier_set_id: str) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT b.*, v.grade, v.kinetic_eligible
        FROM ts_barriers AS b JOIN ts_validations AS v ON v.ts_validation_id=b.ts_validation_id
        WHERE b.barrier_set_id=?
        """,
        (barrier_set_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"accepted barrier set not found: {barrier_set_id}")
    item = dict(row)
    if item["validation_status"] != "accepted" or item["grade"] != "A" or item["kinetic_eligible"] != 1:
        raise ValueError("barrier promotion requires an accepted Grade-A kinetic-eligible TS barrier")
    return item


def _resolve_columns(  # noqa: C901 - one explicit dispatcher mirrors the request schema
    connection: sqlite3.Connection, request: dict[str, Any]
) -> tuple[list[Any], list[dict[str, Any]], str | None]:
    kind = request["promotion_kind"]
    registry_id = request["registry_id"]
    context = _adsorption_context(connection, registry_id) if kind == "adsorption" else _barrier_context(connection, registry_id)
    values: list[Any] = []
    provenance: list[dict[str, Any]] = []
    accepted_energy = False
    allowed_barrier_fields = {
        "barrier_set_id",
        "reaction_id",
        "energy_convention",
        "forward_barrier_ev",
        "reverse_barrier_ev",
        "reaction_energy_ev",
    }
    allowed_ts_validation_fields = {
        "imaginary_frequency_count",
        "principal_imaginary_frequency_cm1",
        "principal_mode_assignment",
        "geometry_status",
        "grade",
        "kinetic_eligible",
        "reviewed_at_excel_serial",
    }
    for header, column in zip(request["workbook"]["headers"], request["columns"], strict=True):
        if not isinstance(column, dict) or column.get("header") != header or not isinstance(column.get("source"), dict):
            raise ValueError(f"column binding for {header!r} is invalid")
        source = column["source"]
        source_type = source.get("type")
        if source_type == "reviewed_metadata":
            value = _reviewed_metadata(source)
            provenance.append({"header": header, "kind": source_type, "reviewed_value": value})
        elif source_type == "existing_workbook_cell":
            if request["workbook"].get("target_row") is None:
                raise ValueError(
                    "existing_workbook_cell is valid only for an existing-row promotion"
                )
            if "expected_value" not in source or not isinstance(
                source["expected_value"], (str, int, float)
            ):
                raise ValueError(
                    "existing_workbook_cell requires a scalar expected_value"
                )
            value = source["expected_value"]
            provenance.append(
                {
                    "header": header,
                    "kind": source_type,
                    "expected_value": value,
                }
            )
        elif kind == "adsorption" and source_type == "result":
            result_id = _require_text(source, "result_id")
            value, result = _result_value(
                connection,
                calculation_id=registry_id,
                result_id=result_id,
                accepted_statuses=ACCEPTED_ADSORPTION_PROMOTION_STATUSES,
            )
            if result["numeric_value"] is not None and str(result["unit"]).lower() == "ev":
                accepted_energy = True
            provenance.append(
                {"header": header, "kind": source_type, "result_id": result_id, "result_name": result["result_name"], "unit": result["unit"]}
            )
        elif kind == "barrier" and source_type == "barrier_field":
            field = _require_text(source, "field")
            if field not in allowed_barrier_fields:
                raise ValueError(f"barrier field cannot be promoted: {field}")
            value = context[field]
            provenance.append({"header": header, "kind": source_type, "field": field})
        elif kind == "barrier" and source_type == "barrier_energy":
            role = _require_text(source, "role")
            result_field = {
                "initial": "initial_result_id",
                "ts": "ts_result_id",
                "final": "final_result_id",
            }.get(role)
            if result_field is None:
                raise ValueError(f"barrier energy role is invalid: {role}")
            result_id = context[result_field]
            result_row = connection.execute(
                "SELECT calculation_id FROM results WHERE result_id=?",
                (result_id,),
            ).fetchone()
            if result_row is None:
                raise ValueError(f"barrier energy result not found: {result_id}")
            value, result = _result_value(
                connection,
                calculation_id=result_row["calculation_id"],
                result_id=result_id,
            )
            provenance.append(
                {
                    "header": header,
                    "kind": source_type,
                    "role": role,
                    "result_id": result_id,
                    "result_name": result["result_name"],
                    "unit": result["unit"],
                }
            )
        elif kind == "barrier" and source_type == "ts_validation_field":
            field = _require_text(source, "field")
            if field not in allowed_ts_validation_fields:
                raise ValueError(f"TS validation field cannot be promoted: {field}")
            validation = connection.execute(
                "SELECT * FROM ts_validations WHERE ts_validation_id=?",
                (context["ts_validation_id"],),
            ).fetchone()
            if validation is None:
                raise ValueError(
                    f"TS validation not found: {context['ts_validation_id']}"
                )
            if field == "principal_imaginary_frequency_cm1":
                frequencies = json.loads(validation["imaginary_frequencies_cm1"] or "[]")
                if not isinstance(frequencies, list) or len(frequencies) != 1:
                    raise ValueError(
                        "principal imaginary frequency promotion requires exactly one mode"
                    )
                value = abs(float(frequencies[0]))
            elif field == "reviewed_at_excel_serial":
                reviewed_at = validation["reviewed_at"]
                if not reviewed_at:
                    raise ValueError("TS validation has no reviewed_at timestamp")
                reviewed_datetime = datetime.fromisoformat(str(reviewed_at))
                excel_epoch = datetime(1899, 12, 30)
                value = (
                    reviewed_datetime.replace(tzinfo=None) - excel_epoch
                ).total_seconds() / 86400
            else:
                value = validation[field]
            if value is None:
                raise ValueError(f"TS validation field has no value: {field}")
            provenance.append(
                {
                    "header": header,
                    "kind": source_type,
                    "field": field,
                    "ts_validation_id": context["ts_validation_id"],
                }
            )
        else:
            raise ValueError(f"column {header!r} has an invalid source for {kind} promotion")
        values.append(value)
    if kind == "adsorption" and not accepted_energy:
        raise ValueError("adsorption promotion requires at least one accepted eV result binding")
    return values, provenance, context.get("calculation_id")


def build_plan(request_path: Path, database: Path = DEFAULT_DATABASE) -> dict[str, Any]:
    request = load_request(request_path)
    workbook = _rooted_path(request["workbook"]["path"], label="workbook path")
    if workbook.suffix.lower() != ".xlsx" or not workbook.is_file():
        raise ValueError(f"workbook must be an existing .xlsx file: {workbook}")
    receipt_path = _rooted_path(request.get("receipt_path") or DEFAULT_RECEIPTS / f"{request['promotion_id']}.json", label="receipt path")
    if receipt_path.exists():
        raise ValueError(f"receipt already exists: {receipt_path}")
    with open_registry(database) as connection:
        _validate_unpromoted(connection, request)
        values, provenance, calculation_id = _resolve_columns(connection, request)
    request_sha256 = sha256_json(request)
    return {
        "schema_version": 1,
        "document_kind": "registry_excel_promotion_plan",
        "promotion_id": request["promotion_id"],
        "promotion_kind": request["promotion_kind"],
        "registry_id": request["registry_id"],
        "calculation_id": calculation_id,
        "request_path": str(request_path),
        "request_sha256": request_sha256,
        "workbook_path": str(workbook),
        "worksheet_name": request["workbook"]["worksheet_name"],
        "header_row": request["workbook"]["header_row"],
        "headers": request["workbook"]["headers"],
        "target_row": request["workbook"].get("target_row"),
        "row_values": values,
        "row_values_sha256": sha256_json(values),
        "source_bindings": provenance,
        "workbook_sha256_before": sha256_file(workbook),
        "receipt_path": str(receipt_path),
        "reviewer": request["review"]["reviewer"],
        "reviewed_at": request["review"]["reviewed_at"],
        "notes": request.get("notes"),
    }


def _load_plan(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or payload.get("document_kind") != "registry_excel_promotion_plan":
        raise ValueError("invalid promotion plan")
    return payload


def _parse_writer_output(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        try:
            result = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(result, dict):
            return result
    raise ValueError("Excel writer did not return a JSON receipt preview")


def _run_writer(plan_path: Path, output: Path, *, node: Path, node_modules: Path, writer: Path) -> dict[str, Any]:
    environment = os.environ.copy()
    environment["NODE_PATH"] = str(node_modules)
    artifact_module = node_modules / "@oai" / "artifact-tool" / "dist" / "artifact_tool.mjs"
    if not artifact_module.is_file():
        raise ValueError(f"@oai/artifact-tool module not found: {artifact_module}")
    environment["REGISTRY_ARTIFACT_TOOL_MODULE"] = artifact_module.as_uri()
    try:
        completed = subprocess.run(
            [str(node), str(writer), "--plan", str(plan_path), "--output", str(output)],
            check=True,
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=environment,
            timeout=WRITER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Excel writer timed out after {WRITER_TIMEOUT_SECONDS} seconds"
        ) from exc
    return _parse_writer_output(completed.stdout)


def apply_plan(plan_path: Path, *, database: Path, node: Path, node_modules: Path, writer: Path = DEFAULT_WRITER) -> dict[str, Any]:
    plan = _load_plan(plan_path)
    request = load_request(Path(plan["request_path"]))
    fresh = build_plan(Path(plan["request_path"]), database)
    if canonical_json(fresh) != canonical_json(plan):
        raise ValueError("promotion plan is stale; regenerate it after reviewing current registry and workbook state")
    workbook = Path(plan["workbook_path"])
    receipt_path = Path(plan["receipt_path"])
    descriptor, temporary_name = tempfile.mkstemp(dir=workbook.parent, prefix=f".{workbook.stem}.promotion.", suffix=".xlsx")
    os.close(descriptor)
    temporary = Path(temporary_name)
    inspect_sidecar = Path(f"{temporary}.inspect.ndjson")
    try:
        writer_result = _run_writer(plan_path, temporary, node=node, node_modules=node_modules, writer=writer)
        if not temporary.is_file() or sha256_file(workbook) != plan["workbook_sha256_before"]:
            raise ValueError("workbook changed while the promotion writer was running")
        row_number = writer_result.get("row_number")
        if not isinstance(row_number, int) or row_number <= 1:
            raise ValueError("Excel writer returned an invalid target row")
        workbook_after = sha256_file(temporary)
        receipt = {
            "schema_version": 1,
            "document_kind": "registry_excel_promotion_receipt",
            "promotion_id": plan["promotion_id"],
            "promotion_kind": plan["promotion_kind"],
            "registry_id": plan["registry_id"],
            "calculation_id": plan["calculation_id"],
            "worksheet_name": plan["worksheet_name"],
            "excel_row_number": row_number,
            "workbook_path": plan["workbook_path"],
            "workbook_sha256_before": plan["workbook_sha256_before"],
            "workbook_sha256_after": workbook_after,
            "written_values_sha256": plan["row_values_sha256"],
            "source_bindings": plan["source_bindings"],
            "reviewer": plan["reviewer"],
            "reviewed_at": plan["reviewed_at"],
            "request_sha256": plan["request_sha256"],
            "created_at": _utc_now(),
            "notes": plan.get("notes"),
        }
        receipt["receipt_sha256"] = sha256_json(receipt)
        with open_registry(database) as connection:
            _validate_unpromoted(connection, request)
            connection.execute(
                """
                INSERT INTO excel_promotions
                (promotion_id, promotion_kind, registry_id, calculation_id, workbook_path, worksheet_name, row_number,
                 workbook_sha256_before, workbook_sha256_after, written_values_sha256, reviewer, reviewed_at,
                 receipt_path, request_sha256, created_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt["promotion_id"], receipt["promotion_kind"], receipt["registry_id"], receipt["calculation_id"],
                    receipt["workbook_path"], receipt["worksheet_name"], receipt["excel_row_number"],
                    receipt["workbook_sha256_before"], receipt["workbook_sha256_after"], receipt["written_values_sha256"],
                    receipt["reviewer"], receipt["reviewed_at"], str(receipt_path), receipt["request_sha256"],
                    receipt["created_at"], receipt["notes"],
                ),
            )
            write_json_atomic(receipt_path, receipt)
            os.replace(temporary, workbook)
        return receipt
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    finally:
        inspect_sidecar.unlink(missing_ok=True)


def _arguments() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Promote accepted registry values to a hash-bound Excel view.")
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="Validate a reviewed request and write a non-mutating promotion plan.")
    plan.add_argument("--request", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    plan.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    apply = commands.add_parser("apply", help="Revalidate and apply a previously generated promotion plan.")
    apply.add_argument("--plan", type=Path, required=True)
    apply.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    apply.add_argument("--node", type=Path, required=True)
    apply.add_argument("--node-modules", type=Path, required=True)
    apply.add_argument("--writer", type=Path, default=DEFAULT_WRITER)
    return parser


def main() -> None:
    args = _arguments().parse_args()
    if args.command == "plan":
        result = build_plan(_request_path(args.request), args.database.resolve())
        write_json_atomic(args.output.resolve(), result)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return
    result = apply_plan(
        args.plan.resolve(), database=args.database.resolve(), node=args.node.resolve(), node_modules=args.node_modules.resolve(), writer=args.writer.resolve()
    )
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
