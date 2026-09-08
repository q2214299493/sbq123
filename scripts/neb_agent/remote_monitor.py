from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Sequence


DEFAULT_SCRIPT = Path(__file__).with_name("check_neb_job.sh")
HOST_PATTERN = re.compile(r"[A-Za-z0-9_.@-]+")
SSH_TIMEOUT_SECONDS = 60


def normalized_script_payload(script: Path = DEFAULT_SCRIPT) -> bytes:
    """Return the Bash monitor as LF-only bytes with exactly one final newline."""
    payload = script.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return payload.rstrip(b"\n") + b"\n"


def remote_command(job_dir: str, detail_lines: int | None = None) -> str:
    """Build the remote Bash command without interpolating unquoted path text."""
    if job_dir == "~":
        quoted_job_dir = '"$HOME"'
    elif job_dir.startswith("~/"):
        quoted_job_dir = '"$HOME"/' + shlex.quote(job_dir[2:])
    else:
        quoted_job_dir = shlex.quote(job_dir)
    if detail_lines is not None:
        if detail_lines < 1:
            raise ValueError("detail_lines must be positive")
    command = "bash -s -- " + quoted_job_dir
    if detail_lines is not None:
        command += f" --detail {detail_lines}"
    return command


def run_remote_monitor(
    host: str,
    job_dir: str,
    *,
    detail_lines: int | None = None,
    script: Path = DEFAULT_SCRIPT,
) -> int:
    """Run the read-only NEB monitor over SSH and return its real exit code."""
    if HOST_PATTERN.fullmatch(host) is None:
        raise ValueError("host contains unsupported characters")
    try:
        completed = subprocess.run(
            ["ssh", host, remote_command(job_dir, detail_lines)],
            input=normalized_script_payload(script),
            check=False,
            timeout=SSH_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"NEB monitor SSH command timed out after {SSH_TIMEOUT_SECONDS} seconds"
        ) from exc
    return completed.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run check_neb_job.sh remotely with an LF-stable stdin payload."
    )
    parser.add_argument("host")
    parser.add_argument("job_dir")
    parser.add_argument("--detail", nargs="?", const=10, type=int, metavar="TAIL_LINES")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run_remote_monitor(args.host, args.job_dir, detail_lines=args.detail)
    except ValueError as exc:
        build_parser().error(str(exc))
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
