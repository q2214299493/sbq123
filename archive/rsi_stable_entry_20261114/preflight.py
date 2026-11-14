"""Offline RSI launcher/protocol proof. Never runs research, auth RPC or inference."""
import argparse
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import sys


def load_owner(source_root):
    sys.path.insert(0, str(source_root.resolve()))
    module = importlib.import_module("scripts.ts_strategy_engine.review_app_server")
    if not Path(module.__file__).resolve().is_relative_to(source_root.resolve()):
        raise ValueError("Imported RSI protocol owner is not the authorized runtime source.")
    return module


def run(args):
    owner = load_owner(args.source_root)
    from scripts.artifact_io import sha256_file, write_json_exclusive

    args.output.mkdir(parents=True, exist_ok=False)
    before = args.profile.read_bytes()
    profile = json.loads(before)
    backup = args.profile.with_name("daily_profile.before_stable_entry_20261114.json")
    with backup.open("xb") as target:
        target.write(before)
    launcher_digest = sha256_file(args.launcher)
    binary = owner.executable(str(args.launcher))
    try:
        result = owner.verify_protocol(binary, args.output / "protocol", 45,
                                       auth_home=Path(profile["auth_home"]))
    except BaseException as error:
        write_json_exclusive(args.output / "failed_preflight.json", {
            "status": "FAIL", "error": str(error), "profile_changed": False,
            "research_started": False, "model_turns_started": 0,
        })
        raise
    if args.profile.read_bytes() != before:
        raise ValueError("Operational profile changed during offline proof; do not install stale evidence.")
    if (sha256_file(args.launcher) != launcher_digest
            or owner.executable(str(args.launcher)) != binary
            or sha256_file(binary) != result["executable_sha256"]):
        raise ValueError("Runtime changed during preflight; preserve evidence, do not change the profile.")
    commands = [json.loads(path.read_text(encoding="utf-8"))
                for path in sorted((args.output / "protocol").glob("command-*.json"))]
    expected = [
        ["--version"], ["app-server", "--help"],
        ["app-server", "generate-json-schema", "--help"], ["features", "list"],
        ["app-server", "generate-json-schema", "--experimental", "--out",
         str(args.output / "protocol" / "schema")],
    ]
    if len(commands) != 5 or [row["argv"][1:] for row in commands] != expected:
        raise ValueError("Offline probe command scope differs; no model-capable command is allowed.")
    if any(row["exit_code"] != 0 for row in commands):
        raise ValueError("A local protocol command failed.")
    report = {
        "status": "PASS", "checked_at": datetime.now(timezone.utc).isoformat(),
        "profile": str(args.profile), "profile_before_sha256": sha256_file(args.profile),
        "backup": str(backup), "backup_sha256": sha256_file(backup),
        "stable_entry": str(args.launcher), "stable_entry_sha256": launcher_digest,
        "runtime_source": str(Path(owner.__file__).resolve()),
        "runtime_source_sha256": sha256_file(Path(owner.__file__)),
        "protocol": result, "offline_commands": [row["argv"][1:] for row in commands],
        "all_command_exits_zero": True, "profile_changed": False,
        "research_started": False, "model_turns_started": 0,
        "live_authentication_tested": False, "model_access_tested": False,
        "scientific_jobs_started": 0,
    }
    write_json_exclusive(args.output / "offline_preflight.json", report)
    print(json.dumps({key: report[key] for key in ("status", "stable_entry", "protocol", "model_turns_started")}, indent=2))


def verify_installed(args):
    owner = load_owner(args.source_root)
    from scripts.artifact_io import sha256_file, write_json_exclusive

    evidence = json.loads((args.output / "offline_preflight.json").read_text(encoding="utf-8"))
    backup = Path(evidence["backup"])
    before, after = backup.read_bytes(), args.profile.read_bytes()
    original, installed = json.loads(before), json.loads(after)
    expected = {**original, "codex": str(args.launcher)}
    if installed != expected:
        raise ValueError("Profile change extends beyond the authorized stable entry.")
    old_token = json.dumps(original["codex"]).encode()
    new_token = json.dumps(str(args.launcher)).encode()
    if before.count(old_token) != 1 or before.replace(old_token, new_token, 1) != after:
        raise ValueError("Profile bytes changed beyond its sole codex string value.")
    binary = owner.executable(installed["codex"])
    checks = {
        "offline_preflight_passed": evidence["status"] == "PASS",
        "only_codex_value_changed": True,
        "backup_unchanged": sha256_file(backup) == evidence["profile_before_sha256"],
        "stable_entry_unchanged": sha256_file(args.launcher) == evidence["stable_entry_sha256"],
        "source_matches_preflight": sha256_file(Path(owner.__file__)) == evidence["runtime_source_sha256"],
        "binary_matches_preflight": sha256_file(binary) == evidence["protocol"]["executable_sha256"],
        "resolved_path_matches": str(binary) == evidence["protocol"]["executable"],
    }
    if not all(checks.values()):
        raise ValueError(checks)
    result = {"status": "PASS", "checks": checks, "profile_after_sha256": sha256_file(args.profile),
              "changed_keys": ["codex"], "model_turns_started": 0, "scientific_jobs_started": 0}
    write_json_exclusive(args.output / "installation_verification.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("phase", choices=("preflight", "verify-installed"))
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--launcher", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    {"preflight": run, "verify-installed": verify_installed}[args.phase](args)
