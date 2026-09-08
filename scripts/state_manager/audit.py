from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from scripts.artifact_io import sha256_file, sha256_text

from .models import ROOT, utc_now
from .projections import (
    DEFAULT_POLICY,
    END_MARKER,
    START_MARKER,
    load_policy,
    module_row_text,
)
from .store import EventStore


JOB_ID = re.compile(r"(?<!\d)9\d{6}(?!\d)")


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    summary: str
    paths: tuple[str, ...] = ()
    review_required: bool = False
    suggested_action: str = ""
    details: dict[str, Any] = field(default_factory=dict)


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _section(text: str, heading: str) -> str:
    match = re.search(rf"(?m)^{re.escape(heading)}\s*$", text)
    if not match:
        return ""
    next_heading = re.search(r"(?m)^## ", text[match.end() :])
    end = match.end() + next_heading.start() if next_heading else len(text)
    return text[match.start() : end]


def _current_step(text: str) -> str:
    match = re.search(
        r"(?ms)^## One Executable Step\s*$\s*(.*?)(?=^## |\Z)",
        text,
    )
    return match.group(1).strip() if match else ""


def _managed_block(text: str, block_id: str) -> str | None:
    start = START_MARKER.format(block_id=block_id)
    end = END_MARKER.format(block_id=block_id)
    if text.count(start) != 1 or text.count(end) != 1:
        return None
    match = re.search(re.escape(start) + r".*?" + re.escape(end), text, re.DOTALL)
    return match.group(0) if match else None


def _audit_task(root: Path, policy: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    path = root / policy["managed_views"]["current_task"]
    if not path.is_file():
        return [Finding("current_task_missing", "error", "Current task file is missing.", (_relative(path, root),), True)]
    text = path.read_text(encoding="utf-8")
    line_count = len(text.splitlines())
    if line_count > int(policy["budgets"]["current_task_max_lines"]):
        findings.append(
            Finding(
                "current_task_over_budget",
                "warning",
                f"Current task has {line_count} lines and exceeds the configured budget.",
                (_relative(path, root),),
                True,
                "Move history into events and keep one executable step.",
            )
        )
    inactive_projection = bool(
        re.search(
            r"(?m)^No active task\. The latest completed task event is\s*$",
            text,
        )
    )
    step_count = len(re.findall(r"(?m)^## One Executable Step\s*$", text))
    if not inactive_projection and step_count != 1:
        findings.append(
            Finding(
                "current_task_step_count",
                "error",
                f"Current task must contain exactly one executable-step section; found {step_count}.",
                (_relative(path, root),),
                True,
            )
        )
    if _managed_block(text, "current_task") is None:
        findings.append(
            Finding(
                "current_task_unmanaged",
                "warning",
                "Current task has not been adopted as a managed projection.",
                (_relative(path, root),),
                True,
                "Generate and approve the initial baseline-adoption proposal.",
            )
        )
    return findings


def _audit_lifecycle_views(root: Path, policy: dict[str, Any]) -> list[Finding]:
    managed = {
        "backlog": "task_backlog_events",
        "error_log": "task_error_events",
        "decisions_log": "task_decision_events",
        "historical_results": "task_history_events",
    }
    missing: list[str] = []
    for view_name, block_id in managed.items():
        path = root / policy["managed_views"][view_name]
        if not path.is_file() or _managed_block(
            path.read_text(encoding="utf-8"), block_id
        ) is None:
            missing.append(_relative(path, root))
    if not missing:
        return []
    return [
        Finding(
            "lifecycle_views_unmanaged",
            "warning",
            "Task lifecycle views have not all adopted their managed projection blocks.",
            tuple(missing),
            True,
            "Review the initial managed-view adoption in the next task-end checkpoint proposal.",
        )
    ]


def _audit_current_state(root: Path, policy: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    path = root / policy["managed_views"]["current_state"]
    if not path.is_file():
        return [Finding("current_state_missing", "error", "Current-state file is missing.", (_relative(path, root),), True)]
    text = path.read_text(encoding="utf-8")
    line_count = len(text.splitlines())
    if line_count > int(policy["budgets"]["current_state_warning_lines"]):
        findings.append(
            Finding(
                "current_state_over_budget",
                "warning",
                f"Current-state view has {line_count} lines and still carries historical detail.",
                (_relative(path, root),),
                True,
                "Compress one independently owned historical section at a time.",
            )
        )
    header = re.search(r"(?m)^State updated:\s*(\d{4}-\d{2}-\d{2})", text)
    gate_dates = re.findall(r"(?m)^### Current Gate[^\n]*(\d{4}-\d{2}-\d{2})", text)
    if header and gate_dates and header.group(1) < max(gate_dates):
        findings.append(
            Finding(
                "current_state_header_stale",
                "warning",
                f"State header is {header.group(1)} but a current gate is dated {max(gate_dates)}.",
                (_relative(path, root),),
                False,
                "Project the latest accepted state-event timestamp into the header.",
            )
        )
    history_limit = int(policy["budgets"]["historical_section_warning_lines"])
    for match in re.finditer(r"(?m)^## (.+)$", text):
        heading = f"## {match.group(1)}"
        section = _section(text, heading)
        count = len(section.splitlines())
        if count > history_limit:
            findings.append(
                Finding(
                    "duplicate_or_historical_overload",
                    "warning",
                    f"Section '{match.group(1)}' has {count} lines and mixes current state with historical flow.",
                    (_relative(path, root),),
                    True,
                    "Keep a managed current-gate block and migrate durable history separately.",
                    {"heading": heading, "line_count": count},
                )
            )
    return findings


def _audit_module_gate(root: Path, policy: dict[str, Any]) -> list[Finding]:
    task_path = root / policy["managed_views"]["current_task"]
    module_path = root / policy["managed_views"]["module_map"]
    if not task_path.is_file() or not module_path.is_file():
        return []
    task = task_path.read_text(encoding="utf-8")
    if "modules/transition_state_search/README.md" not in task:
        return []
    step_ids = JOB_ID.findall(_current_step(task))
    if not step_ids:
        return []
    current_job = step_ids[0]
    module_map = module_path.read_text(encoding="utf-8")
    row_match = re.search(r"(?m)^\| `transition_state_search` \|.*$", module_map)
    if row_match and current_job not in row_match.group(0):
        return [
            Finding(
                "module_gate_stale",
                "warning",
                f"Transition-state module gate does not reference current-step job {current_job}.",
                (_relative(module_path, root), _relative(task_path, root)),
                False,
                "Project a module_gate_changed event after evidence review.",
                {"current_job_id": current_job, "module_row": row_match.group(0)},
            )
        ]
    return []


def _latest_status_mentions(text: str) -> dict[str, str]:
    mentions: dict[str, str] = {}
    for match in JOB_ID.finditer(text):
        nearby = text[match.end() : match.end() + 240]
        next_job = JOB_ID.search(nearby)
        if next_job:
            nearby = nearby[: next_job.start()]
        status = re.search(
            r"^`?\s*(?:is|was|reached)\s+(?:scheduler\s+)?`?(PEND|RUN|DONE|EXIT)`?\b",
            nearby,
            re.IGNORECASE,
        )
        if status is None:
            status = re.search(
                r"(?is)^.{0,220}?\b(?:is|was|reached)\s+scheduler\s+`?(PEND|RUN|DONE|EXIT)`?\b",
                nearby,
            )
        if status:
            mentions[match.group(0)] = status.group(1).upper()
    return mentions


def _current_gate_text(text: str) -> str:
    blocks = re.findall(
        r"(?ms)^### Current Gate.*?(?=^### |^## |\Z)",
        text,
    )
    return "\n".join(blocks)


def _audit_status_conflicts(root: Path, policy: dict[str, Any]) -> list[Finding]:
    views = policy["managed_views"]
    sources = {
        views["current_task"]: "full",
        views["current_state"]: "current_gate",
        views["module_map"]: "full",
        views["error_log"]: "full",
    }
    by_job: dict[str, dict[str, str]] = {}
    for relative, scope in sources.items():
        path = root / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if scope == "current_gate":
            text = _current_gate_text(text)
        for job_id, status in _latest_status_mentions(text).items():
            by_job.setdefault(job_id, {})[relative] = status
    findings: list[Finding] = []
    for job_id, statuses in sorted(by_job.items()):
        if len(set(statuses.values())) < 2:
            continue
        findings.append(
            Finding(
                "current_status_conflict",
                "error",
                f"Current repository views disagree on scheduler status for job {job_id}.",
                tuple(sorted(statuses)),
                True,
                "Confirm the live scheduler state, record one evidence-bound event, and supersede stale views.",
                {"job_id": job_id, "statuses": statuses},
            )
        )
    return findings


def _audit_projection_manifest(root: Path, policy: dict[str, Any]) -> list[Finding]:
    path = root / policy["paths"]["projection_manifest"]
    if not path.is_file():
        return [Finding("projection_manifest_missing", "warning", "Projection manifest is missing.", (_relative(path, root),))]
    payload = json.loads(path.read_text(encoding="utf-8"))
    findings: list[Finding] = []
    for key, record in payload.get("projections", {}).items():
        target_name, _, block_id = key.partition("#")
        target = root / target_name
        if not target.is_file():
            findings.append(Finding("managed_target_missing", "error", f"Managed target is missing: {target_name}", (target_name,), True))
            continue
        managed_unit = record.get("managed_unit")
        if managed_unit:
            if managed_unit.get("kind") != "module_row":
                findings.append(
                    Finding(
                        "projection_manifest_invalid",
                        "error",
                        f"Unsupported managed projection unit: {key}",
                        (target_name,),
                        True,
                    )
                )
                continue
            try:
                row = module_row_text(
                    target.read_text(encoding="utf-8"),
                    str(managed_unit["id"]),
                )
            except (KeyError, ValueError):
                actual = None
            else:
                actual = sha256_text(row)
            expected = record.get("managed_unit_sha256")
        elif block_id and record.get("managed_block_sha256"):
            block = _managed_block(target.read_text(encoding="utf-8"), block_id)
            actual = sha256_text(block) if block is not None else None
            expected = record["managed_block_sha256"]
        else:
            actual = sha256_file(target)
            expected = record.get("target_sha256_after")
        if expected and actual != expected:
            findings.append(
                Finding(
                    "managed_projection_drift",
                    "error",
                    f"Managed projection changed outside the recorded event: {key}",
                    (target_name,),
                    True,
                    "Import the manual change as a reviewed event or restore the projection.",
                )
            )
    return findings


def _audit_events(store: EventStore) -> list[Finding]:
    try:
        store.latest_by_entity()
    except (OSError, ValueError) as error:
        return [Finding("event_ledger_invalid", "error", str(error), review_required=True)]
    return []


def _git_lines(root: Path, *args: str) -> list[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        return []
    return completed.stdout.splitlines()


def _audit_repository_items(root: Path, policy: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    allowed_roots = {
        str(item)
        for item in policy["repository_item_policy"]["allowed_root_directories"]
    }
    unexpected_names: set[str] = set()
    for path in root.iterdir():
        ignored = subprocess.run(
            ["git", "check-ignore", "--quiet", "--", path.name],
            cwd=root,
            check=False,
            capture_output=True,
        ).returncode == 0
        if path.is_dir() and path.name not in allowed_roots and not ignored:
            unexpected_names.add(path.name.lower())
            findings.append(
                Finding(
                    "unexpected_root_item",
                    "warning",
                    f"Root directory is outside the repository contract: {path.name}",
                    (path.name,),
                    True,
                    "Confirm ownership and uniqueness before preserving, archiving, or deleting it.",
                )
            )
    candidates = {str(item).lower() for item in policy["repository_item_policy"]["candidate_patterns"]}
    for line in _git_lines(root, "status", "--porcelain=v1"):
        if not line.startswith("?? "):
            continue
        relative = line[3:].strip().replace("\\", "/").rstrip("/")
        leaf = Path(relative).name.lower()
        if leaf in candidates and leaf not in unexpected_names:
            findings.append(
                Finding(
                    "obsolete_item_candidate",
                    "warning",
                    f"Untracked repository item matches an obsolete-item pattern: {relative}",
                    (relative,),
                    True,
                    "Inspect uniqueness before proposing archive or deletion.",
                )
            )
    worktree_paths: list[str] = []
    for line in _git_lines(root, "worktree", "list", "--porcelain"):
        if line.startswith("worktree "):
            worktree_paths.append(line.removeprefix("worktree ").strip())
    root_text = str(root.resolve()).lower()
    for path in worktree_paths:
        if str(Path(path).resolve()).lower() == root_text:
            continue
        findings.append(
            Finding(
                "external_worktree_review",
                "warning",
                f"Additional Git worktree requires ownership review: {path}",
                (path,),
                True,
                "Audit only; version 1 never deletes external worktrees.",
            )
        )
    return findings


def audit_repository(
    *,
    project_root: Path = ROOT,
    policy_path: Path = DEFAULT_POLICY,
    phase: str = "start",
) -> dict[str, Any]:
    if phase not in {"start", "end"}:
        raise ValueError("audit phase must be start or end")
    root = project_root.resolve()
    policy = load_policy(policy_path)
    events_dir = root / policy["paths"]["events"]
    store = EventStore(
        events_dir=events_dir,
        schema_path=root / "configs" / "state_handoff_event.schema.json",
        project_root=root,
    )
    findings: list[Finding] = []
    module_readme = root / "modules" / "state_handoff" / "README.md"
    if not module_readme.is_file():
        findings.append(
            Finding(
                "state_handoff_module_missing",
                "error",
                "Module map declares state_handoff but its implementation module is missing.",
                ("modules/state_handoff",),
                True,
            )
        )
    findings.extend(_audit_events(store))
    findings.extend(_audit_task(root, policy))
    findings.extend(_audit_lifecycle_views(root, policy))
    findings.extend(_audit_current_state(root, policy))
    findings.extend(_audit_module_gate(root, policy))
    findings.extend(_audit_status_conflicts(root, policy))
    findings.extend(_audit_projection_manifest(root, policy))
    findings.extend(_audit_repository_items(root, policy))
    findings.sort(key=lambda item: (item.severity != "error", item.code, item.paths))
    review_findings = [finding for finding in findings if finding.review_required]
    return {
        "schema_version": 1,
        "phase": phase,
        "generated_at": utc_now(),
        "project_root": str(root),
        "counts": {
            "error": sum(finding.severity == "error" for finding in findings),
            "warning": sum(finding.severity == "warning" for finding in findings),
            "review_required": len(review_findings),
        },
        "findings": [asdict(finding) for finding in findings],
        "review_requests": [
            {
                "finding_code": finding.code,
                "question": finding.summary,
                "options": [
                    {"value": "review", "label": "Review exact evidence"},
                    {"value": "preserve", "label": "Preserve current state"},
                ],
                "paths": list(finding.paths),
            }
            for finding in review_findings
        ],
    }
