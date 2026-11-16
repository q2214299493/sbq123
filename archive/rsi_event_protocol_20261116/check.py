"""Offline trace replay and one optional protocol-only model turn;no research retry."""
import argparse
import json
from pathlib import Path
import sys
import time
import tomllib

SOURCE = Path("C:/Users/86177/Desktop/rsi-usage-dashboard-20261030")
RUNTIME = Path("C:/Users/86177/Desktop/fe110_rsi_experiments/rsi_runtime_policy_20261030")
ORIGINAL = RUNTIME / "runs/mkm_c1_c2_inventory_20261116_v1"
OUT = RUNTIME / "event_protocol_repair_20261116_v1"
sys.path.insert(0, str(SOURCE))

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive  # noqa:E402
from scripts.ts_strategy_engine.review_app_server import executable, start_session, verify_protocol  # noqa:E402
from scripts.ts_strategy_engine.review_events import ReviewEvents  # noqa:E402
from scripts.ts_strategy_engine.review_live import LiveStdio, settings  # noqa:E402


class Collector(ReviewEvents):
    def __init__(self, thread, turn):
        self.thread_id, self.turn_id = thread, turn
        self.backend_warnings, self.messages, self.message_phases = [], {}, {}
        self.turn_completed, self.token_usage = False, None
        self.prompt = {"protocol_smoke": "Return exactly the JSON object with ok=true. No tools or file reads."}


def offline():
    if OUT.exists():
        raise ValueError("Existing repair evidence;inspect it rather than overwrite")
    OUT.mkdir()
    profile_path = RUNTIME / "daily_profile.json"
    before = profile_path.read_bytes()
    profile = json.loads(before)
    journal = ORIGINAL / "journal.jsonl"
    before_journal = sha256_file(journal)
    before_receipt = sha256_file(ORIGINAL / "run_receipt.json")
    rows = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    thread = next(row["data"]["result"]["thread"]["id"] for row in rows if row["kind"] == "received" and "thread" in row["data"].get("result", {}))
    turn = next(row["data"]["turn"]["turn"]["id"] for row in rows if row["kind"] == "turn_started")
    recorder = Collector(thread, turn)
    notifications = [row["data"] for row in rows if row["kind"] == "received" and "method" in row["data"]]
    if notifications[0]["method"] != "configWarning":
        raise ValueError("Historical first event differs from the diagnosed failure")
    for event in notifications:
        recorder._notification(event["method"], event.get("params", {}))
    binary = executable(profile["codex"])
    protocol = verify_protocol(binary, OUT / "protocol", 45, auth_home=Path(profile["auth_home"]))
    warning_schema = load_json_object(OUT / "protocol/schema/v2/ConfigWarningNotification.json")
    if warning_schema["required"] != ["summary"] or warning_schema["properties"]["summary"]["type"] != "string":
        raise ValueError("Current warning schema differs;review before inference")
    if (profile_path.read_bytes() != before or sha256_file(journal) != before_journal
            or sha256_file(ORIGINAL / "run_receipt.json") != before_receipt):
        raise ValueError("Original configuration or failed evidence changed")
    result = {"status": "PASS", "runtime_source": str(SOURCE), "review_events_sha256": sha256_file(SOURCE / "scripts/ts_strategy_engine/review_events.py"),
        "protocol": protocol, "replayed_notifications": len(notifications), "warnings_preserved": len(recorder.backend_warnings),
        "original_journal_sha256": before_journal, "original_receipt_sha256": before_receipt,
        "profile_unchanged": True, "original_failures_unchanged": True, "model_turns_started": 0, "scientific_jobs": 0}
    write_json_exclusive(OUT / "offline_preflight.json", result)
    print({k: result[k] for k in ("status", "replayed_notifications", "warnings_preserved", "model_turns_started")})


def live():
    proof = load_json_object(OUT / "offline_preflight.json")
    if proof["status"] != "PASS" or proof["review_events_sha256"] != sha256_file(SOURCE / "scripts/ts_strategy_engine/review_events.py"):
        raise ValueError("Offline proof missing or stale")
    directory = OUT / "live"
    directory.mkdir()
    profile_path = RUNTIME / "daily_profile.json"
    profile_bytes = profile_path.read_bytes()
    profile = json.loads(profile_bytes)
    home = Path(profile["auth_home"])
    config = home / "config.toml"
    config_bytes = config.read_bytes()
    current = tomllib.loads(config_bytes.decode("utf-8"))
    roots = [Path(key) for key in current["permissions"]["review-model"]["filesystem"]
        if "diagnosis-workspaces/" in key and not key.endswith("/model_input.json")]
    if len(roots) != 1 or current != settings(home, roots[0], [roots[0] / "model_input.json"], credential_store="file"):
        raise ValueError("Existing isolated configuration differs;do not modify permissions")
    events = []
    transport = None
    receipt = {"status": "BLOCKED", "model_turn_start_attempts": 0, "model_turns_started": 0,
        "scientific_jobs": 0, "research_requests_retried": 0, "native_tool_executions": 0}
    try:
        transport = LiveStdio(executable(profile["codex"]), directory, 90, lambda kind, data: events.append({"kind": kind, "data": data}),
            home, [roots[0] / "model_input.json"], workspace=roots[0], credential_store="file")
        session = start_session(transport, roots[0], profile["model"], profile["effort"], [],
            instructions="Protocol self-test only. Return exactly {\"ok\":true}. No tools,files,research or delegation.")
        collector = Collector(session["thread"]["id"], None)
        receipt["model_turn_start_attempts"] = 1
        turn = transport.rpc("turn/start", {"threadId": collector.thread_id, "model": profile["model"], "effort": profile["effort"],
            "approvalPolicy": "never", "environments": [], "permissions": transport.model_profile,
            "outputSchema": {"type": "object", "properties": {"ok": {"type": "boolean", "enum": [True]}}, "required": ["ok"], "additionalProperties": False},
            "input": [{"type": "text", "text": json.dumps(collector.prompt, ensure_ascii=False)}]})
        collector.turn_id = turn["turn"]["id"]
        receipt["model_turns_started"] = 1
        deadline = time.monotonic() + 60
        while not collector.turn_completed:
            if time.monotonic() >= deadline:
                raise TimeoutError("Single-turn protocol smoke deadline")
            event = transport.receive()
            item = event.get("params", {}).get("item", {})
            if "id" in event or item.get("type") not in {None, "userMessage", "agentMessage", "reasoning"}:
                raise ValueError("Unexpected native activity during protocol-only smoke")
            collector._notification(event.get("method"), event.get("params", {}))
        if len(collector.messages) != 1 or json.loads(next(iter(collector.messages.values()))) != {"ok": True}:
            raise ValueError("Unmodified smoke response differs")
        receipt.update(status="PASS", completed_turn=True, response={"ok": True}, backend_warnings=collector.backend_warnings,
            token_usage=collector.token_usage, thread_id=collector.thread_id, turn_id=collector.turn_id)
    except (OSError, ValueError, TypeError, KeyError, TimeoutError, EOFError) as exc:
        receipt["problem"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        if transport is not None:
            transport.close()
        receipt["profile_unchanged"] = profile_path.read_bytes() == profile_bytes
        receipt["isolated_permissions_unchanged"] = config.read_bytes() == config_bytes
        write_json_exclusive(directory / "receipt.json", receipt)
        write_json_exclusive(directory / "events.json", {"events": events})
    if not receipt["profile_unchanged"] or not receipt["isolated_permissions_unchanged"]:
        raise ValueError("Unexpected configuration change")
    print({k: receipt[k] for k in ("status", "model_turns_started", "research_requests_retried", "scientific_jobs")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("phase", choices=("offline", "live"))
    {"offline": offline, "live": live}[parser.parse_args().phase]()
