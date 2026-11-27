"""Optional path-compatible launchers for a separately provisioned historical case."""

from pathlib import Path


def launchers(role):
    if role not in ("mkm", "kmc"):
        raise ValueError("Unknown role")
    stub = (
        '"""Explicit compatibility view of the installed role."""\n'
        "import sys\nfrom sbq123.common.compat import activate\n"
        f'activate("{role}", _package=sys.modules[__name__])\n'
    )
    result = {"scripts/__init__.py": stub.encode()}
    if role == "mkm":
        result["scripts/kinetic_data/comparison_point.py"] = (
            '"""Standalone launcher for the installed MKM point reader."""\n'
            'from sbq123.mkm.point_reader import main\nif __name__=="__main__": main()\n'
        ).encode()
    return result


def add_launchers(root, role):
    for rel, raw in launchers(role).items():
        p = Path(root) / rel
        if p.is_file() and p.read_bytes() == raw:
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("xb") as f:
            f.write(raw)
