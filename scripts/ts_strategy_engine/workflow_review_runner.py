"""One independent bounded review; immutable host receipts and schema-2 projection."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import uuid

from scripts.artifact_io import sha256_file, sha256_json, write_json_exclusive
from .learning_evidence import exact_keys, observe
from .review_app_server import executable, probe_backend, redacted, start_session
from .review_evidence import EvidenceTools, TOOLS, new_output, safe_file
from .workflow_improvement import _expected_advice, _policy, _source, policy_status


def reference(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha256_file(path)}


def load_trial(store: Path, request: dict) -> dict:
    exact_keys(request, {"schema_version", "trial", "candidate_id", "policy_id", "scope",
                         "case_id", "task_id", "input_sha256"})
    if type(request["schema_version"]) is not int or request["schema_version"] != 1:
        raise ValueError("review request schema must be 1")
    trial_path = Path(request["trial"]["path"])
    safe_file(trial_path, trial_path.parent)
    trial = _source(request["trial"])
    candidate = _policy(store, request["candidate_id"])
    if candidate["kind"] != "candidate" or request["policy_id"] not in {
            request["candidate_id"], candidate["parent_id"]}:
        raise ValueError("review policy is not a member of this frozen pair")
    selected = _policy(store, request["policy_id"])
    if policy_status(store, request["policy_id"])["status"] == "REJECTED":
        raise ValueError("rejected review policy")
    contract = candidate["evaluation_contract"]
    if any(trial[k] != candidate[k] for k in ("scope", "provenance", "inputs", "evaluation_contract")) \
            or request["scope"] != candidate["scope"]:
        raise ValueError("frozen trial scope/input/contract mismatch")
    task = next((t for t in contract["tasks"] if t["case_id"] == request["case_id"]), None)
    if task is None or any(request[k] != task[k] for k in ("task_id", "input_sha256")):
        raise ValueError("review task/input identity mismatch")
    advice = _expected_advice(selected, request["policy_id"])
    row = next(r for r in advice["recommendations"] if r["case_id"] == task["case_id"])
    fields = row["ts_strategy_fields_to_review"]
    if set(fields) != set(TOOLS.values()) or len(fields) != 2:
        raise ValueError("runner supports only the existing two geometry review fields")
    tools = EvidenceTools(trial["materials"], trial_path.parent)
    for identity, material in tools.materials.items():
        if material["sha256"] == candidate["inputs"]["answers"]["sha256"] \
                or tools.path(identity).is_relative_to(store.resolve()):
            raise ValueError("reference answers or workflow decisions cannot be model evidence")
    case = next(c for c in _source(trial["inputs"]["public"])["cases"] if c["case_id"] == task["case_id"])
    sources = {m["sha256"]: {k: m[k] for k in ("path", "sha256")} for m in tools.materials.values()}
    if any(e["source_sha256"] not in sources for e in case["evidence"]):
        raise ValueError("frozen materials do not own this case's original evidence")
    observe([{**sources[e["source_sha256"]], "pointer": e["pointer"], "value": e["value"]} for e in case["evidence"]])
    return {"trial": trial, "trial_root": trial_path.parent.resolve(), "tools": tools,
            "task": task, "advice": advice, "order": fields, "request": request, "store": store.resolve(),
            "context": {"schema_version": 2, "policy_id": request["policy_id"], "scope": candidate["scope"],
                        "provenance": candidate["provenance"], "contract_sha256": sha256_json(contract), **task}}


class ReviewRun:
    """Only host tool completions produce actions/checks; final prose has no authority."""

    def __init__(self, loaded: dict, output: Path, model: str, effort: str, timeout: float):
        if not model.strip() or effort not in {"minimal", "low", "medium", "high", "xhigh"} \
                or isinstance(timeout, bool) or not 0 < timeout <= 3600:
            raise ValueError("explicit model/effort and process timeout (0, 3600] required")
        output = new_output(output, [loaded["trial_root"], loaded["store"]])
        (output / "workspace").mkdir()
        self.loaded, self.output = loaded, output.resolve()
        self.model, self.effort, self.timeout = model, effort, timeout
        self.run_id = str(uuid.uuid4())
        self.context = {k: v for k, v in loaded["context"].items() if k != "required_checks"}
        self.calls, self.cache, self.checks = [], {}, {}
        self.thread_id = self.session_id = self.turn_id = None
        self.incomplete, self.problem, self.finished = False, None, False
        self.deadline = time.monotonic() + timeout
        self.record("prepared", {"run_id": self.run_id, **self.context, "model": model, "effort": effort,
                                "request": loaded["request"],
                                "max_tool_calls": 8, "process_timeout_seconds": timeout,
                                "runtime_sources": {name: sha256_file(Path(__file__).with_name(name)) for name in
                                                   ("workflow_review_runner.py", "review_evidence.py", "review_app_server.py")}})
        write_json_exclusive(self.output / "advice.json", loaded["advice"])

    def record(self, kind: str, value: dict):
        payload = {"kind": kind, "time_utc": datetime.now(timezone.utc).isoformat(), **redacted(value)}
        # Host-owned append-only journal; flushed before tool execution/response.
        with (self.output / "journal.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def protocol(self, direction, message):
        self.record("protocol", {"direction": direction, "message": message})

    def _stop(self, reason: str):
        self.incomplete, self.problem = True, reason
        self.record("stopped", {"reason": reason})

    def tool_call(self, params: dict) -> dict:
        self.record("tool_arrived", {"session_id": self.session_id, "params": params})
        if params.get("threadId") != self.thread_id or params.get("turnId") != self.turn_id \
                or not isinstance(params.get("callId"), str) or not params["callId"]:
            self._stop("tool session/turn/call identity mismatch")
            return EvidenceTools.response({"error": self.problem}, False)
        key = (self.session_id, self.turn_id, params["callId"])
        fingerprint = sha256_json(params)
        if key in self.cache:
            saved = self.cache[key]
            if saved["fingerprint"] != fingerprint:
                self._stop("conflicting retransmitted call identity")
                return EvidenceTools.response({"error": self.problem}, False)
            self.record("retransmission", {"call_id": params["callId"], "event_id": saved["event_id"]})
            return saved["response"]
        tool = params.get("tool")
        if tool not in TOOLS or params.get("namespace") not in {None, ""}:
            self._stop("unapproved native/namespace/write/delegation tool")
            return EvidenceTools.response({"error": self.problem}, False)
        if len(self.calls) >= 8 or time.monotonic() >= self.deadline or self.incomplete:
            self._stop("review tool/process budget exhausted or run already interrupted")
            return EvidenceTools.response({"error": self.problem}, False)
        field = TOOLS[tool]
        first = list(dict.fromkeys(call["field"] for call in self.calls))
        if field not in first and field != self.loaded["order"][len(first)]:
            self._stop("tool order differs from frozen policy")
            return EvidenceTools.response({"error": self.problem}, False)
        event_id = f"{self.run_id}:{len(self.calls)}"
        call = {"event_id": event_id, "sequence": len(self.calls), "field": field,
                "result": None, "status": "STARTED", "session_id": self.session_id,
                "thread_id": self.thread_id, "turn_id": self.turn_id, "call_id": params["callId"]}
        self.calls.append(call)
        self.record("action_started", {**self.context, **call, "arguments": params.get("arguments")})
        try:
            result = self.loaded["tools"].execute(tool, params.get("arguments"))
            call.update(status="COMPLETED", result="READ_COMPLETED")
            self.checks[f"{field}_evidence_read"] = True
            self.checks["source_and_task_identity"] = True
            response = EvidenceTools.response(result, True)
            if time.monotonic() >= self.deadline:
                self._stop("host tool exceeded process wall-clock budget")
        except TimeoutError:
            raise  # STARTED receipt survives; export marks the unreturned call INTERRUPTED.
        except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            call.update(status="FAILED", result="READ_FAILED")
            response = EvidenceTools.response({"error": str(exc)}, False)
            self._stop(f"host evidence tool failed: {exc}")
        self.record("action_finished", {**self.context, **call, "response": response})
        self.cache[key] = {"fingerprint": fingerprint, "event_id": event_id, "response": response}
        return response

    def drive(self, transport, *, synthetic: bool = False) -> dict:
        """Synthetic transport exercise only until a backend with verified read confinement exists."""
        if not synthetic or self.context["provenance"] != "synthetic":
            raise ValueError("live model review blocked: evidence-only native read confinement unverified")
        self.record("synthetic_transport", {"not_a_real_model_review": True})
        try:
            session = start_session(transport, self.output / "workspace", self.model, self.effort,
                                    self.loaded["tools"].specs())
            self.thread_id, self.session_id = session["thread"]["id"], session["thread"]["sessionId"]
            if not self.thread_id or not self.session_id:
                raise ValueError("backend session identity missing")
            self.record("session", {"session": session, "run_id": self.run_id})
            public = _source(self.loaded["trial"]["inputs"]["public"])
            case = next(c for c in public["cases"] if c["case_id"] == self.context["case_id"])
            prompt = {"case": case, "review_order": self.loaded["order"],
                      "evidence_ids": sorted(self.loaded["tools"].materials),
                      "required_checks": self.loaded["task"]["required_checks"],
                      "instruction": "Review using only the supplied tools, in order. Human judgments remain pending. Maximum 8 calls, one turn. No calculations, acceptance or delegation."}
            turn = transport.rpc("turn/start", {"threadId": self.thread_id, "model": self.model,
                         "effort": self.effort, "approvalPolicy": "never", "environments": [],
                         "sandboxPolicy": {"type": "readOnly", "networkAccess": False},
                         "input": [{"type": "text", "text": json.dumps(prompt, ensure_ascii=False)}]})
            self.turn_id = turn["turn"]["id"]
            while not self.incomplete:
                if time.monotonic() >= self.deadline:
                    raise TimeoutError("review process wall-clock budget exhausted")
                message = transport.receive()
                self.protocol("received", message)
                method, params = message.get("method"), message.get("params", {})
                if method == "item/tool/call" and "id" in message:
                    response = self.tool_call(params)
                    transport.send({"id": message["id"], "result": response})
                    self.protocol("sent", {"id": message["id"], "result": response})
                elif "id" in message and method:
                    transport.send({"id": message["id"], "error": {"code": -32601, "message": "host rejects extra tools"}})
                    self._stop("unapproved server request")
                elif method in {"thread/started", "thread/status/changed", "thread/tokenUsage/updated"}:
                    if params.get("threadId", params.get("thread", {}).get("id")) != self.thread_id:
                        raise ValueError("notification thread mismatch")
                elif method in {"turn/completed", "turn/started", "item/started", "item/completed", "item/agentMessage/delta"}:
                    if params.get("threadId") != self.thread_id or (
                            params.get("turn", {}).get("id", params.get("turnId")) != self.turn_id):
                        raise ValueError("notification session/turn mismatch")
                    item = params.get("item", {})
                    if method.startswith("item/") and item.get("type") not in {None, "agentMessage", "reasoning", "dynamicToolCall"}:
                        raise ValueError("native tool activity/delegation forbidden")
                    if method == "turn/completed":
                        self.finished = params["turn"]["status"] == "completed"
                        if not self.finished:
                            self._stop("turn failed/interrupted")
                        break
                else:
                    raise ValueError(f"unexpected protocol notification: {method}")
        except (EOFError, TimeoutError, ValueError, OSError, KeyError, TypeError) as exc:
            self._stop(f"review interrupted: {exc}")
        finally:
            transport.close()
        return self.export()

    def export(self) -> dict:
        for call in self.calls:
            if call["status"] == "STARTED":
                call["status"] = "INTERRUPTED"
                self.record("action_unreturned", {**self.context, **call})
                self.incomplete = True
        complete = self.finished and not self.incomplete
        checks = [{"check_id": key, "result": self.checks.get(key)} for key in self.loaded["task"]["required_checks"]]
        raw = {**self.context, "actions": [{k: c[k] for k in ("event_id", "sequence", "field", "result")} for c in self.calls],
               "checks": checks}
        path = self.output / "raw.json"
        write_json_exclusive(path, raw)
        source = reference(path)
        def observation(pointer, value):
            return {**source, "pointer": pointer, "value": value}
        trace = {**self.context, "source": source, "advice": reference(self.output / "advice.json"),
                 "actions": [{"event_id": c["event_id"], "field": c["field"],
                              "observation": observation(f"/actions/{i}/result", c["result"])} for i, c in enumerate(self.calls)],
                 # Retain all raw checks/actions; partial projection cannot become a complete evaluation.
                 "checks": [{"check_id": c["check_id"], "observation": observation(f"/checks/{i}/result", c["result"])}
                            for i, c in enumerate(checks)] if complete else []}
        write_json_exclusive(self.output / "trace.json", trace)
        result = {"run_id": self.run_id, "status": "RECORDED" if complete else "INCOMPLETE",
                  "provenance": self.context["provenance"], "actual_tool_calls": len(self.calls),
                  "session_id": self.session_id, "thread_id": self.thread_id, "problem": self.problem,
                  "session_independence": "NEW_SESSION" if self.session_id else "NOT_TESTED",
                  "model_read_scope": "NOT_VERIFIED", "log_completeness": complete,
                  "required_checks": checks, "trace": reference(self.output / "trace.json"),
                  "scientific_success": "NOT_EVALUATED", "automatic_acceptance": False}
        write_json_exclusive(self.output / "result.json", result)
        return result


def run_review(store: Path, request_path: Path, output: Path, *, model: str, effort: str,
               timeout: float = 120, codex: str | None = None, probe: bool = False, execute: bool = False) -> dict:
    request = _source(reference(request_path))
    loaded = load_trial(store, request)
    run = ReviewRun(loaded, output, model, effort, timeout)
    result = {"status": "PREPARED", "output": str(run.output), "policy_id": request["policy_id"],
              "order": loaded["order"], "model_calls": 0, "max_tool_calls": 8,
              "process_timeout_seconds": timeout, "model_read_scope": "NOT_VERIFIED"}
    if probe or execute:
        try:
            result["backend"] = probe_backend(executable(codex), run.output / "backend", timeout,
                                              model, effort, loaded["tools"].specs())
        except (OSError, ValueError, TimeoutError) as exc:
            result.update(status="BLOCKED", reason=f"backend protocol probe failed: {exc}")
    if execute:
        # Current backend cannot attest native read restrictions. There is deliberately no override flag.
        result.update(status="BLOCKED", reason=result.get("reason") or result["backend"]["blocking_reason"])
    write_json_exclusive(run.output / "result.json", result)
    return result
