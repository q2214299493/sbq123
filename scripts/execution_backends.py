from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "execution_backends.yaml"


@dataclass(frozen=True)
class SchedulerBackend:
    name: str
    server_alias: str


@dataclass(frozen=True)
class GpuBackend:
    hostname: str
    scheduler: str
    remote_write_boundary: str


@dataclass(frozen=True)
class ExecutionBackends:
    vasp: SchedulerBackend
    gpu: GpuBackend


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping")
    return value


def _text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} must be non-empty")
    return text


def load_execution_backends(path: Path = DEFAULT_CONFIG) -> ExecutionBackends:
    """Load and validate the runtime backend authority contract."""

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    contract = _mapping(payload, "execution backend contract")
    if contract.get("version") != 3:
        raise ValueError("execution backend contract must use version 3")
    authority = _mapping(contract.get("authority"), "execution backend authority")
    if authority.get("direct_gpu_to_vasp_handoff") != "forbidden":
        raise ValueError("direct GPU-to-VASP handoff must remain forbidden")
    if authority.get("automatic_remote_submission") != "forbidden":
        raise ValueError("automatic remote submission must remain forbidden")

    scientific_rules = _mapping(
        contract.get("scientific_rules"), "execution backend scientific rules"
    )
    if scientific_rules.get("grade_a_requires_validated_vibrational_mode") is not True:
        raise ValueError("Grade A must require a validated vibrational mode")
    if scientific_rules.get("dimer_grade_a_requires_bidirectional_connectivity") is not False:
        raise ValueError("DIMER Grade A must not require bidirectional connectivity")
    if scientific_rules.get("dimer_bidirectional_connectivity_role") != (
        "optional_diagnostic_not_ts_acceptance_gate"
    ):
        raise ValueError("DIMER bidirectional connectivity must remain optional diagnostic evidence")
    if scientific_rules.get("neb_ci_neb_bidirectional_connectivity_policy") != (
        "required_unchanged"
    ):
        raise ValueError("NEB/CI-NEB connectivity policy changed without approval")

    backends = _mapping(contract.get("backends"), "execution backends")
    vasp = _mapping(backends.get("vasp"), "VASP backend")
    gpu = _mapping(backends.get("aqcat_gpu"), "AQCat GPU backend")
    vasp_backend = SchedulerBackend(
        name=_text(vasp.get("scheduler"), "VASP scheduler"),
        server_alias=_text(vasp.get("ssh_alias"), "VASP SSH alias"),
    )
    gpu_scheduler = _mapping(gpu.get("scheduler"), "AQCat GPU scheduler")
    gpu_backend = GpuBackend(
        hostname=_text(gpu.get("observed_hostname"), "AQCat GPU hostname"),
        scheduler=_text(gpu_scheduler.get("type"), "AQCat GPU scheduler type"),
        remote_write_boundary=_text(
            gpu.get("remote_write_boundary"), "AQCat GPU write boundary"
        ),
    )
    if vasp_backend.name != "LSF":
        raise ValueError("authoritative VASP backend must use LSF")
    if gpu_backend.remote_write_boundary != "/home/sbq/sbq":
        raise ValueError("AQCat GPU write boundary must remain /home/sbq/sbq")
    return ExecutionBackends(vasp=vasp_backend, gpu=gpu_backend)


def require_vasp_backend(
    server_alias: Any,
    scheduler: Any,
    *,
    path: Path = DEFAULT_CONFIG,
) -> SchedulerBackend:
    backend = load_execution_backends(path).vasp
    if (str(server_alias), str(scheduler)) != (
        backend.server_alias,
        backend.name,
    ):
        raise ValueError(
            "scheduler evidence does not match the configured authoritative VASP backend"
        )
    return backend


def require_gpu_backend(
    server_alias: Any,
    scheduler: Any,
    *,
    path: Path = DEFAULT_CONFIG,
) -> GpuBackend:
    backend = load_execution_backends(path).gpu
    if (str(server_alias), str(scheduler)) != (
        backend.hostname,
        backend.scheduler,
    ):
        raise ValueError(
            "scheduler evidence does not match the configured AQCat GPU backend"
        )
    return backend


def require_gpu_write_path(
    value: Any,
    *,
    path: Path = DEFAULT_CONFIG,
) -> str:
    backend = load_execution_backends(path).gpu
    boundary = PurePosixPath(backend.remote_write_boundary)
    candidate = PurePosixPath(_text(value, "AQCat GPU write path"))
    if candidate != boundary and boundary not in candidate.parents:
        raise ValueError("AQCat GPU write path escapes the configured write boundary")
    return candidate.as_posix()
