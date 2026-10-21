"""Bounded final-frame extraction plus whole-OUTCAR SHA; no remote writes."""
import base64
import hashlib
import json
import re
import subprocess
from pathlib import Path

RECORDS: list[dict]


def final_cycle_metadata(oszicar):
    finals = list(re.finditer(r"^\s*(\d+)\s+F\s*=", oszicar, re.MULTILINE))
    electronic = list(re.finditer(r"^\s*(?:DAV|RMM|CGA):\s*(\d+)", oszicar, re.MULTILINE))
    if not finals or not electronic or electronic[-1].start() > finals[-1].start():
        raise ValueError("OSZICAR final cycle is incomplete")
    return int(finals[-1].group(1)), int(electronic[-1].group(1))

def read_final(record):
    root = Path(record["remote_dir"]).expanduser()
    path = root / "OUTCAR"
    before = path.stat()
    with path.open("rb") as handle:
        start = max(0, before.st_size - 262144)
        handle.seek(start)
        tail = handle.read(262144)
    force_pos = tail.rfind(b"TOTAL-FORCE (eV/Angst)")
    if force_pos < 0:
        raise ValueError("final force block missing from bounded tail")
    line_start = tail.rfind(b"\n", 0, force_pos) + 1
    matches = list(re.finditer(rb"Iteration\s+(\d+)\s*\(\s*(\d+)\s*\)", tail[:line_start]))
    last = matches[-1] if matches else None
    reached = b"aborting loop because EDIFF is reached" in tail[last.start():line_start] if last else None
    rows, tokens, raw = [], [], b""
    for line in tail[line_start:].splitlines(keepends=True):
        raw += line
        fields = line.split()
        if len(fields) == 6:
            try:
                values = [float(v) for v in fields]
            except ValueError:
                continue
            rows.append(values)
            tokens.append([v.decode("ascii") for v in fields[:3]])
        elif rows:
            break
    if len(rows) != record["atom_count"]:
        raise ValueError("final force block atom count mismatch")
    energies = re.findall(rb"free\s+energy\s+TOTEN\s*=\s*([-+.0-9Ee]+)", tail[line_start:])
    if len(energies) != 1:
        raise ValueError("ambiguous final force/TOTEN association")
    digest = subprocess.check_output(["sha256sum", str(path)], timeout=30).decode().split()[0]
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("OUTCAR changed while extracting final frame")
    if b"General timing and accounting informations" not in tail:
        raise ValueError("source is not normally terminated")
    files = {}
    for name in ("POSCAR", "CONTCAR", "INCAR", "KPOINTS", "OSZICAR"):
        p = root / name
        if p.stat().st_size > 2000000:
            raise ValueError("small source exceeds declared budget:" + name)
        files[name] = base64.b64encode(p.read_bytes()).decode("ascii")
    step, iteration = final_cycle_metadata(base64.b64decode(files["OSZICAR"]).decode("utf-8", "replace"))
    if last and tuple(map(int, last.groups())) != (step, iteration):
        raise ValueError("OUTCAR/OSZICAR final cycle mismatch")
    frame = {"ionic_step": step, "electronic_iteration": iteration, "EDIFF_marker_before_force": reached,
             "positions_A": [r[:3] for r in rows], "position_tokens": tokens,
             "forces_eV_per_A": [r[3:] for r in rows], "source_byte_range": [start + line_start, start + line_start + len(raw)],
             "force_table_base64": base64.b64encode(raw).decode("ascii"), "toten_eV": float(energies[0]),
             "iteration_source": "OUTCAR_and_OSZICAR" if last else "OSZICAR_final_complete_cycle;OUTCAR_iteration_outside_tail"}
    return {"record": record, "frames": [frame], "total_steps": step, "OUTCAR_sha256": digest,
            "OUTCAR_bytes": before.st_size, "normal_completion": True, "files": files,
            "ionic_converged": b"reached required accuracy" in tail,
            "POTCAR_sha256": hashlib.sha256((root / "POTCAR").read_bytes()).hexdigest()}


if __name__ == "__main__":
    for record in RECORDS:  # injected by the bounded work-side collector
        print(json.dumps(read_final(record)), flush=True)
