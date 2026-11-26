"""Bundle the active sources as resources to avoid deep intermediate paths in Windows wheel builds."""
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from setuptools.command.build_py import build_py


class BuildRelease(build_py):
    def run(self):
        super().run()
        base = Path(__file__).resolve().parent
        roles = json.loads((base / "roles.json").read_bytes())
        sources = {entry["source"]: entry["sha256"] for entry in roles.values() if "source" in entry}
        target = Path(self.build_lib) / "sbq123_v31" / "role-sources.zip"
        with ZipFile(target, "w") as archive:
            for relative, expected in sorted(sources.items()):
                data = (base / relative).read_bytes()
                if hashlib.sha256(data).hexdigest() != expected:
                    raise ValueError(f"Changed release source {relative}")
                archive.writestr(ZipInfo(relative), data, compress_type=ZIP_DEFLATED)
