"""Render the canonical Sunboquan LSF launcher used by VASP builders.

Keeping scheduler boilerplate here avoids each input builder embedding a
slightly different shell script.  This module only renders text; it never
submits or executes a job.
"""

from __future__ import annotations

from pathlib import Path


TEMPLATE = Path(__file__).with_name("templates") / "sunboquan_vasp.lsf"


def render_sunboquan_lsf(cores: int, *, template: Path = TEMPLATE) -> str:
    """Return a validated VASP LSF script for ``cores`` MPI ranks."""

    if isinstance(cores, bool) or int(cores) <= 0:
        raise ValueError("VASP LSF core count must be a positive integer")
    source = template.read_text(encoding="ascii")
    rendered = source.replace("__CORES__", str(int(cores)))
    if "__CORES__" in rendered:
        raise ValueError(f"unresolved placeholder in VASP LSF template: {template}")
    return rendered if rendered.endswith("\n") else rendered + "\n"
