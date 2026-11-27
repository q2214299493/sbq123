"""Report read-only resource snapshots for the configured GPU and CPU servers."""
from __future__ import annotations

import argparse
import shlex
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import yaml

from scripts.execution_backends import DEFAULT_CONFIG


PROBE = b"""\
root=$1
host=$(hostname -s) || exit 1
printf 'Hostname: %s\\nWork root: %s\\n' "$host" "$root"
failed=0
if [ -d "$root" ] && [ -w "$root" ] && [ -x "$root" ] && canonical=$(realpath -e -- "$root"); then
    printf 'Writable directory: %s\\n' "$canonical"
else
    printf 'Work root is missing or inaccessible\\n'
    failed=1
fi

printf '\\nGPUs (index, UUID, model, total MiB, free MiB, utilization %%):\\n'
if nvidia-smi --query-gpu=index,uuid,name,memory.total,memory.free,utilization.gpu --format=csv,noheader,nounits 2>&1; then
    printf 'Compute process GPU UUIDs (blank means none reported):\\n'
    nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader 2>&1 || failed=1
else
    failed=1
fi

printf '\\nSlurm node resources:\\n'
if command -v scontrol >/dev/null 2>&1; then
    if node=$(scontrol -d -o show node "$host" 2>&1); then
        printf '%s\\n' "$node" | awk '{for (i=1; i<=NF; i++) if ($i ~ /^(State|Gres|GresUsed|CfgTRES|AllocTRES)=/) print $i}'
    else
        printf '%s\\n' "$node"
        failed=1
    fi
else
    printf 'Slurm client unavailable\\n'
fi
exit "$failed"
"""


CPU_PROBE = b"""\
root=$1
host=$(hostname -s) || exit 1
printf 'Hostname: %s\\nWork root: %s\\n' "$host" "$root"
failed=0
if [ -d "$root" ] && [ -w "$root" ] && [ -x "$root" ] && canonical=$(realpath -e -- "$root"); then
    printf 'Writable directory: %s\\n' "$canonical"
else
    printf 'Work root is missing or inaccessible\\n'
    failed=1
fi
printf '\\nLSF host states (cluster totals, not a task allocation):\\n'
if hosts=$(bhosts -w 2>&1); then
    printf '%s\\n' "$hosts" | awk 'NR>1 {n++; s[$2]++} END {print "Host records:",n; for(k in s) print k,s[k]}'
else
    printf '%s\\n' "$hosts"
    failed=1
fi
printf '\\nLSF queues:\\n'
if queues=$(bqueues -w 2>&1); then
    printf '%s\\n' "$queues" | awk 'NR==1 {print "QUEUE STATUS PEND RUN"; next} {print $1,$3,$9,$10}'
else
    printf '%s\\n' "$queues"
    failed=1
fi
exit "$failed"
"""


def probe(backend: dict[str, Any]) -> tuple[str, bool]:
    ssh = backend.get("ssh") or {"alias": backend["ssh_alias"]}
    argv = [
        "ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
        "-o", "ConnectTimeout=8", "-o", "IdentitiesOnly=yes",
    ]
    if "alias" in ssh:
        destination = ssh["alias"]
    else:
        argv.extend(["-i", ssh["identity_file"], "-p", str(ssh["port"])])
        destination = f"{ssh['user']}@{ssh['host']}"
    argv.extend(["--", destination, f"sh -s -- {shlex.quote(backend['remote_write_boundary'])}"])
    script = CPU_PROBE if backend.get("role") == "authoritative_first_principles_calculation" else PROBE
    try:
        result = subprocess.run(argv, input=script, capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"Resource check failed: {exc}", False
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace").strip()
    return output, result.returncode == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--include-cpu", action="store_true", help="also check sunboquan-codex and its LSF scheduler")
    args = parser.parse_args(argv)
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    backends = [
        backend for backend in config["backends"].values()
        if backend.get("role") == "candidate_acceleration_only"
    ]
    if not backends:
        parser.error("no GPU servers configured")
    if args.include_cpu:
        backends.append(config["backends"]["vasp"])

    with ThreadPoolExecutor(max_workers=len(backends)) as executor:
        results = list(executor.map(probe, backends))
    for backend, (output, complete) in zip(backends, results, strict=True):
        status = "snapshot" if complete else "incomplete; availability unknown"
        print(f"[{backend['display_name']}] {status}\n{output}\n")
    print("Snapshot only: task software, CUDA allocation, model/input hashes, and execution authority require task-specific preflight.")
    return 0 if all(complete for _, complete in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
