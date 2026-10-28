"""Native Windows read/deny preflight and existing-account stdio transport; no model turn here."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import time
import tomllib

from scripts.artifact_io import sha256_file, sha256_json, write_json_exclusive
from .review_app_server import DISABLED_FEATURES, Stdio, child_environment, redacted, stderr_capture, verify_protocol
from .review_evidence import _no_links


MODEL_PROFILE = "review-model"
CLIENT_PROFILE = "review-client"
ACCOUNT_PROVIDER = "review-chatgpt-account"
CREDENTIAL_STORES = {"keyring", "file"}


@contextmanager
def admission_stage(record, name: str):
    """First failure is recorded at its actual boundary, before any model turn."""
    record("admission_stage", {"stage": name, "state": "STARTED"})
    try:
        yield
    except (OSError, ValueError, TimeoutError, EOFError, KeyError, TypeError) as exc:
        record("admission_stage", {"stage": name, "state": "FAILED", "error_type": type(exc).__name__, "error": str(exc)})
        raise
    record("admission_stage", {"stage": name, "state": "PASSED"})


def settings(home: Path, workspace: Path, evidence_paths: list[Path], *, credential_store: str = "keyring") -> dict:
    if credential_store not in CREDENTIAL_STORES:
        raise ValueError("credential store must be explicitly keyring or file")
    common = {":root": "deny", ":minimal": "read", workspace.as_posix(): "read",
              **{p.as_posix(): "read" for p in evidence_paths}}
    return {"default_permissions": MODEL_PROFILE, "approval_policy": "never", "web_search": "disabled",
            "cli_auth_credentials_store": credential_store, "windows": {"sandbox": "mxc"},
            "features": {**{k: False for k in DISABLED_FEATURES}, "unbounded_connection_retries": False},
            "model_provider": ACCOUNT_PROVIDER,
            "model_providers": {ACCOUNT_PROVIDER: {"name": "Existing managed ChatGPT account", "wire_api": "responses", "requires_openai_auth": True,
                                          "supports_websockets": False, "request_max_retries": 0, "stream_max_retries": 0}},
            "permissions": {
                MODEL_PROFILE: {"filesystem": {**common, home.as_posix(): "deny"}, "network": {"enabled": False}},
                CLIENT_PROFILE: {"filesystem": {**common, home.as_posix(): "write"}, "network": {"enabled": True}}}}


def _toml(document: dict, prefix: str = "") -> str:
    """Serialize this small explicit configuration, not the user's personal config."""
    lines = []
    for key, value in document.items():
        if not isinstance(value, dict):
            literal = str(value).lower() if isinstance(value, bool) else json.dumps(value)
            lines.append(f"{json.dumps(key)} = {literal}")
    for key, value in document.items():
        if isinstance(value, dict):
            section = f"{prefix}.{json.dumps(key)}" if prefix else json.dumps(key)
            lines.extend([f"\n[{section}]", _toml(value, section)])
    return "\n".join(lines) + "\n"


def configure(home: Path, workspace: Path, evidence_paths: list[Path], *, credential_store: str = "keyring") -> dict:
    _no_links(home.absolute(), missing_ok=True)
    if home.resolve().is_relative_to(workspace.resolve()):
        raise ValueError("authentication home cannot be model workspace")
    home.mkdir(parents=True, exist_ok=True)
    expected = settings(home.resolve(), workspace.resolve(), [p.resolve() for p in evidence_paths], credential_store=credential_store)
    path = home / "config.toml"
    if path.exists():
        existing = tomllib.loads(path.read_text(encoding="utf-8"))
        if existing == {"cli_auth_credentials_store": credential_store}:
            # Promote only the isolated login bootstrap, never personal or arbitrary config.
            path.write_text(_toml(expected), encoding="utf-8")
        elif existing != expected:
            raise ValueError("authentication home has a different configuration; do not overwrite it")
    else:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(_toml(expected))
    return expected


def native_probe(binary: Path, home: Path, workspace: Path, directory: Path, timeout: float) -> dict:
    """Exercise OS enforcement for native commands, not pretend that these are model calls."""
    allowed = workspace / "read-canary.txt"
    denied = directory / "outside-canary.txt"
    write_target = workspace / "must-not-write.txt"
    for path, text in ((allowed, "SAFE_READ_CANARY"), (denied, "SAFE_OUTSIDE_CANARY")):
        if path == allowed and path.exists():
            if path.read_bytes() != text.encode("ascii"):
                raise ValueError("existing read canary has unexpected content")
        else:
            with path.open("x", encoding="ascii") as handle:
                handle.write(text)
    environment = child_environment(home)
    records = []
    deadline = time.monotonic() + timeout
    for profile in (MODEL_PROFILE, CLIENT_PROFILE):
        operations = [("allowed", ["type", str(allowed)]), ("outside", ["type", str(denied)]),
                      ("write", ["echo", "FORBIDDEN_WRITE", ">", str(write_target)])]
        for name, arguments in operations:
            command = [str(binary), "sandbox", "--include-managed-config", "--permission-profile", profile,
                       "-C", str(workspace), "--", "cmd.exe", "/d", "/c", *arguments]
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("read/deny probe budget exhausted")
            try:
                completed = subprocess.run(command, env=environment, capture_output=True, timeout=remaining,
                                           creationflags=subprocess.CREATE_NO_WINDOW)
            except (subprocess.TimeoutExpired, OSError) as exc:
                records.append({"profile": profile, "operation": name, "argv": command, "exit_code": None,
                                "error": redacted(str(exc)), "timed_out": isinstance(exc, subprocess.TimeoutExpired),
                                "stdout": redacted((getattr(exc, "stdout", None) or b"").decode("utf-8", errors="replace")),
                                "stderr": redacted((getattr(exc, "stderr", None) or b"").decode("utf-8", errors="replace"))})
                write_json_exclusive(directory / "native-permission-probe.json", {"records": records, "passed": False})
                if isinstance(exc, subprocess.TimeoutExpired):
                    raise TimeoutError("native permission command exceeded probe deadline") from exc
                raise
            captured = stderr_capture(completed.stderr)
            records.append({"profile": profile, "operation": name, "exit_code": completed.returncode,
                            "argv": command, "stdout": redacted(completed.stdout.decode("utf-8", errors="replace")),
                            "stderr": captured["text"], "stderr_capture": captured})
            if name == "allowed" and (completed.returncode != 0 or completed.stdout != b"SAFE_READ_CANARY"):
                write_json_exclusive(directory / "native-permission-probe.json", {"records": records, "passed": False})
                raise ValueError("allowed canary failed; native preflight stopped at first error")
    passed = all(r["exit_code"] == 0 and r["stdout"] == "SAFE_READ_CANARY" if r["operation"] == "allowed"
                 else r["exit_code"] != 0 and "SAFE_OUTSIDE_CANARY" not in r["stdout"] for r in records)
    passed = passed and not write_target.exists()
    result = {"records": records, "passed": passed, "probed_surface": "native Windows MXC commands",
              "model_invoked_probe": False, "whole_filesystem_isolation": "UNKNOWN"}
    write_json_exclusive(directory / "native-permission-probe.json", result)
    if not passed:
        raise ValueError("native read/deny/write probes failed")
    return result


def auth_visibility_probe(binary: Path, home: Path, workspace: Path, directory: Path, timeout: float) -> dict:
    """Read auth mode only; do not read/copy credentials, log out, log in or alter permissions."""
    base = [str(binary), "login", "status"]
    commands = [("host", base), ("native_client", [str(binary), "sandbox", "--include-managed-config",
        "--permission-profile", CLIENT_PROFILE, "-C", str(workspace), "--", *base])]
    records = []
    deadline = time.monotonic() + timeout
    for surface, command in commands:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            records.append({"surface": surface, "exit_code": None, "error": "auth visibility budget exhausted"})
            break
        try:
            completed = subprocess.run(command, env=child_environment(home), cwd=workspace, capture_output=True,
                timeout=remaining, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            records.append({"surface": surface, "argv": command, "exit_code": completed.returncode,
                "stdout": redacted(completed.stdout.decode("utf-8", errors="replace")), "stderr": stderr_capture(completed.stderr)})
        except (OSError, subprocess.TimeoutExpired) as exc:
            records.append({"surface": surface, "exit_code": None, "error": redacted(str(exc))})
            break
    codes = {row["surface"]: row["exit_code"] for row in records}
    status = "AUTH_VISIBILITY_UNRESOLVED"
    if codes.get("host") == 0 and codes.get("native_client") is not None:
        status = "CLI_AUTH_VISIBLE_BUT_ACCOUNT_RPC_EMPTY" if codes["native_client"] == 0 else "HOST_LOGIN_NOT_VISIBLE_TO_NATIVE_CLIENT"
    result = {"status": status, "records": records, "model_turns_started": 0,
              "config_sha256": sha256_file(home / "config.toml"), "permissions_changed": False}
    write_json_exclusive(directory / "auth-visibility-probe.json", result)
    return result


class LiveStdio(Stdio):
    """Admission requires real local configuration, OS probes and managed ChatGPT auth."""

    def __init__(self, binary: Path, directory: Path, timeout: float, record, home: Path, evidence_paths: list[Path],
                 *, workspace: Path | None = None, credential_store: str = "keyring"):
        if os.name != "nt":
            raise ValueError("this live backend requires validated native Windows MXC; other platforms are unverified")
        self.admitted = False
        workspace = workspace or directory / "workspace"
        deadline = time.monotonic() + timeout
        with admission_stage(record, "local_protocol"):
            compatibility = verify_protocol(binary, directory / "protocol", min(timeout, 30), auth_home=home)
        with admission_stage(record, "isolated_configuration"):
            expected = configure(home, workspace, evidence_paths, credential_store=credential_store)
        self.model_profile = MODEL_PROFILE
        self.account_provider = ACCOUNT_PROVIDER
        self.evidence = {**compatibility, "config_sha256": sha256_file(home / "config.toml"), "settings": expected,
                         "executable_sha256": sha256_file(binary)}
        with admission_stage(record, "native_permissions"):
            self.evidence["native_probes"] = native_probe(binary, home, workspace, directory, min(timeout, 30))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("live preflight budget exhausted")
        with admission_stage(record, "app_server_launch"):
            super().__init__(binary, directory, remaining, record, auth_home=home, client_profile=CLIENT_PROFILE, workspace=workspace)
        try:
            with admission_stage(record, "initialize"):
                self.rpc("initialize", {"clientInfo": {"name": "workflow_review", "version": "2"},
                                        "capabilities": {"experimentalApi": True, "explicitGatewayOauth": True}})
                self.send({"method": "initialized"})
                self.initialized = True
            with admission_stage(record, "effective_configuration"):
                configuration = self.rpc("config/read", {"includeLayers": True})
                layers = configuration.get("layers") or []
                matched = [layer for layer in layers if layer.get("config", {}).get("permissions") == expected["permissions"]]
                if not matched or sha256_file(home / "config.toml") != self.evidence["config_sha256"]:
                    raise ValueError("effective named filesystem configuration not confirmed")
                if configuration["config"].get("model_provider") != ACCOUNT_PROVIDER:
                    raise ValueError("managed-account provider configuration not applied")
            with admission_stage(record, "mcp_inventory"):
                servers = self.rpc("mcpServerStatus/list", {})
                if servers.get("data") or servers.get("nextCursor"):
                    raise ValueError("unexpected MCP surface in isolated configuration")
            with admission_stage(record, "chatgpt_authentication"):
                auth = self.rpc("account/read", {"refreshToken": False})
                account = auth.get("account") or {}
                self.evidence["auth"] = {"type": account.get("type"), "requiresOpenaiAuth": auth.get("requiresOpenaiAuth")}
                self.evidence["effective_permissions_sha256"] = sha256_json(matched[0]["config"]["permissions"])
                record("preflight", self.evidence)
                if account.get("type") != "chatgpt" or not auth.get("requiresOpenaiAuth"):
                    if not account:
                        proof = auth_visibility_probe(binary, home, workspace, directory, max(0.01, min(30, deadline - time.monotonic())))
                        self.evidence["auth_visibility"] = proof
                        record("auth_visibility", proof)
                        raise ValueError(f"isolated account unavailable: {proof['status']}; see auth-visibility-probe.json")
                    raise ValueError("admission requires managed ChatGPT authentication, not another auth type")
            self.admitted = True
        except BaseException:
            self.close()
            raise
