"""Bounded stdio protocol transport/probe. No automatic model turn or permission upgrade."""
from __future__ import annotations

import base64
from collections import deque
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive


DISABLED_FEATURES = (
    "shell_tool", "unified_exec", "apps", "plugins", "hooks", "browser_use",
    "browser_use_external", "browser_use_full_cdp_access", "in_app_browser", "browser_annotation_api", "computer_use", "image_generation",
    "view_image", "multi_agent", "code_mode_host", "remote_plugin", "skill_search",
    "daemon_auto_start",
)
MAX_MESSAGE = 1024 * 1024


def executable(value: str | None) -> Path:
    found = Path(value) if value else Path(shutil.which("codex") or "missing-codex")
    if found.suffix.lower() in {".cmd", ".bat"}:
        # The bundled Windows shim points to a versioned executable; never use shell=True.
        candidates = list((found.parent.parent / "bin").glob("*/codex.exe"))
        if len(candidates) != 1:
            raise ValueError("supply --codex with the actual codex.exe path")
        found = candidates[0]
    found = found.resolve(strict=True)
    if not found.is_file():
        raise ValueError("Codex executable required")
    return found


def redacted(value):
    """Keep protocol evidence without persisting authentication tokens."""
    if isinstance(value, dict):
        return {k: "[REDACTED]" if any(s in k.lower() for s in
                ("token", "secret", "authorization", "password", "api_key", "apikey", "credential"))
                else redacted(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redacted(v) for v in value]
    if isinstance(value, str) and ("Bearer " in value or "sk-" in value):
        return "[REDACTED credential-like text]"
    return value


class Stdio:
    """One child process, one absolute deadline, no retries or resumed sessions."""

    def __init__(self, binary: Path, directory: Path, timeout: float, record):
        self.deadline = time.monotonic() + timeout
        self.record, self.pending, self.messages = record, deque(), queue.Queue(maxsize=256)
        self.serial = 0
        home = directory / "codex-home"
        home.mkdir()
        environment = os.environ.copy()
        environment["CODEX_HOME"] = str(home)
        # A probe needs no credentials. Do not inherit model/API authentication variables.
        for key in list(environment):
            if any(term in key.upper() for term in ("API_KEY", "AUTH_TOKEN", "ACCESS_TOKEN")):
                del environment[key]
        flags = [part for feature in DISABLED_FEATURES for part in ("--disable", feature)]
        self.process = subprocess.Popen(
            [str(binary), "app-server", "--stdio", *flags, "-c", 'web_search="disabled"'],
            cwd=directory / "workspace", env=environment, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        self.watchdog = threading.Timer(timeout, self._expire)
        self.watchdog.daemon = True
        self.watchdog.start()

    def _expire(self):
        if self.process.poll() is None:
            self.process.kill()  # Hard bound also covers blocked writes or an unresponsive peer.

    def _read(self):
        try:
            while True:
                line = self.process.stdout.readline(MAX_MESSAGE + 1)
                if not line:
                    raise EOFError("app-server stream ended")
                if len(line) > MAX_MESSAGE:
                    raise ValueError("protocol message exceeds 1 MiB")
                self.messages.put(json.loads(line), timeout=1)
        except (EOFError, ValueError, OSError, queue.Full) as exc:
            try:
                self.messages.put(exc, timeout=1)
            except queue.Full:
                self.process.terminate()

    def send(self, message: dict):
        self.record("sent", message)
        data = (json.dumps(message) + "\n").encode()
        if len(data) > MAX_MESSAGE:
            raise ValueError("outgoing protocol message exceeds 1 MiB")
        self.process.stdin.write(data)
        self.process.stdin.flush()

    def receive(self) -> dict:
        if self.pending:
            return self.pending.popleft()
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("review process wall-clock budget exhausted")
        try:
            item = self.messages.get(timeout=remaining)
        except queue.Empty as exc:
            raise TimeoutError("review process wall-clock budget exhausted") from exc
        if isinstance(item, Exception):
            raise item
        self.record("received", item)
        return item

    def rpc(self, method: str, params: dict) -> dict:
        self.serial += 1
        identity = self.serial
        self.send({"id": identity, "method": method, "params": params})
        deferred = []
        try:
            while True:
                message = self.receive()
                if message.get("id") == identity and "method" not in message:
                    if "error" in message:
                        raise ValueError(f"{method} rejected: {redacted(message['error'])}")
                    return message["result"]
                deferred.append(message)
        finally:
            self.pending.extend(deferred)

    def close(self):
        self.watchdog.cancel()
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=2)
        for stream in (self.process.stdin, self.process.stdout):
            stream.close()


def start_session(transport, workspace: Path, model: str, effort: str, tools: list) -> dict:
    transport.rpc("initialize", {"clientInfo": {"name": "workflow_review", "version": "1"},
                  "capabilities": {"experimentalApi": True, "explicitGatewayOauth": True}})
    transport.send({"method": "initialized"})
    result = transport.rpc("thread/start", {
        "model": model, "approvalPolicy": "never", "sandbox": "read-only",
        "cwd": str(workspace.resolve()), "ephemeral": True, "environments": [],
        "runtimeWorkspaceRoots": [str(workspace.resolve())], "selectedCapabilityRoots": [],
        "baseInstructions": "Only the two supplied review tools are permitted. No delegation or other tools.",
        "developerInstructions": "Read-only evidence review. Never execute calculations or accept a strategy.",
        "config": {"model_reasoning_effort": effort, "web_search": "disabled"}, "dynamicTools": tools,
    })
    thread = result["thread"]
    if thread.get("parentThreadId") or thread.get("forkedFromId") or thread["turns"] \
            or not thread["ephemeral"] or result["model"] != model \
            or result["approvalPolicy"] != "never" or result["sandbox"]["type"] != "readOnly":
        raise ValueError("new session/model/permission identity mismatch")
    if result.get("reasoningEffort") != effort:
        raise ValueError("reasoning effort not confirmed by backend")
    return result


def probe_backend(binary: Path, directory: Path, timeout: float, model: str, effort: str, tools: list) -> dict:
    """Local help/schema/session probe only. Never sends turn/start or copies auth."""
    directory.mkdir()
    (directory / "workspace").mkdir()
    deadline = time.monotonic() + timeout
    def command(arguments):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("protocol probe budget exhausted")
        try:
            result = subprocess.run([str(binary), *arguments], capture_output=True, timeout=remaining,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError("local protocol command exceeded probe deadline") from exc
        if result.returncode:
            raise ValueError(f"Codex protocol probe failed: {arguments}, exit={result.returncode}")
        return result.stdout.decode("utf-8")
    version = command(["--version"]).strip()
    help_text = command(["app-server", "--help"])
    schema_help = command(["app-server", "generate-json-schema", "--help"])
    features = command(["features", "list"])
    if "--stdio" not in help_text or "--out" not in schema_help \
            or any(feature not in {line.split()[0] for line in features.splitlines() if line.split()}
                   for feature in DISABLED_FEATURES):
        raise ValueError("local CLI lacks required protocol/feature controls")
    schema = directory / "schema"
    command(["app-server", "generate-json-schema", "--experimental", "--out", str(schema)])
    start = load_json_object(schema / "v2" / "ThreadStartParams.json")
    turn = load_json_object(schema / "v2" / "TurnStartParams.json")
    call = load_json_object(schema / "DynamicToolCallParams.json")
    if not {"dynamicTools", "environments", "runtimeWorkspaceRoots"} <= start["properties"].keys() \
            or not {"threadId", "input", "sandboxPolicy", "effort"} <= turn["properties"].keys() \
            or not {"arguments", "callId", "threadId", "turnId", "tool"} <= call["properties"].keys():
        raise ValueError("incompatible app-server protocol")
    events = []
    def record(direction, message):
        events.append({"direction": direction, "message": redacted(message)})
    transport = Stdio(binary, directory, max(0.01, deadline - time.monotonic()), record)
    canary = directory / "outside-canary.txt"
    canary.write_text("OUTSIDE_MATERIAL_CANARY", encoding="utf-8")
    try:
        session = start_session(transport, directory / "workspace", model, effort, tools)
        native = transport.rpc("fs/readFile", {"path": str(canary.resolve())})
        outside_read = base64.b64decode(native["dataBase64"]) == b"OUTSIDE_MATERIAL_CANARY"
        mcp = transport.rpc("mcpServerStatus/list", {})
        result = {"version": version, "executable": str(binary), "executable_sha256": sha256_file(binary),
                  "protocol_compatible": True, "session": redacted(session), "new_session_verified": True,
                  "mcp_servers": redacted(mcp), "disabled_features": list(DISABLED_FEATURES),
                  "native_client_rpc_reads_outside_workspace": outside_read,
                  "model_read_scope_verified": False, "model_turns_started": 0,
                  "blocking_reason": "readOnly has no evidence-only read allowlist; native tool catalog/OS read confinement unverified. Client fs RPC is host authority, not a model escape test."}
    finally:
        transport.close()
        write_json_exclusive(directory / "protocol.json", events)
    write_json_exclusive(directory / "probe.json", result)
    return result
