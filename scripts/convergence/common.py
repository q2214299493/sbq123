from __future__ import annotations

import re
from pathlib import Path

from scripts.scientific_validation import finite_number

TOTEN_PATTERN = re.compile(r"\bfree\s+energy\s+TOTEN\b(.*)$")
# Existing submission timeout, shared with the legacy convergence submitter.
EXTERNAL_COMMAND_TIMEOUT_SECONDS = 300


def last_matching_float(path: Path, pattern: re.Pattern[str]) -> float | None:
    if not path.exists():
        return None
    value = None
    for line in path.read_text(errors="ignore").splitlines():
        match = pattern.search(line)
        if match:
            value = float(match.group(1))
    return value


def extract_toten(outcar: Path) -> float | None:
    """Extract the last finite TOTEN; malformed records are errors, not fallback."""
    if not outcar.exists():
        return None
    value = None
    with outcar.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            record = TOTEN_PATTERN.search(line)
            if record:
                fields = record.group(1).split()
                if len(fields) != 3 or fields[0] != "=" or fields[2] != "eV":
                    raise ValueError(f"Malformed TOTEN record: {outcar}")
                if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?", fields[1]):
                    raise ValueError(f"TOTEN must be a finite VASP numeric token: {outcar}")
                value = finite_number(fields[1], "TOTEN energy")
    return value
