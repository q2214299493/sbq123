"""Content identity of the installed code and resources used by a release worker."""

import base64
from functools import lru_cache
from hashlib import sha256
from importlib import metadata

from sbq123.common.kinetic_model.contracts import identity


@lru_cache(maxsize=4)
def _checked_digest(owner):
    distribution = metadata.distribution("sbq123-" + owner)
    hashes = {}
    for path in distribution.files or ():
        name = path.as_posix()
        if not name.startswith("sbq123/") or name.endswith(".pyc"):
            continue
        data = path.locate().read_bytes()
        digest = sha256(data)
        expected = base64.urlsafe_b64encode(digest.digest()).decode().rstrip("=")
        if path.hash is None or path.hash.mode != "sha256" or path.hash.value != expected:
            raise ValueError(f"Installed distribution integrity failure: {name}")
        hashes[name] = digest.hexdigest()
    if not hashes:
        raise ValueError("Empty installed release inventory")
    return distribution.version, identity(hashes)


def installed_role(role):
    if role not in ("mkm", "kmc"):
        raise ValueError("Unknown solver role")
    return {
        name: {"version": version, "installed_files_sha256": digest}
        for name in ("common", role)
        for version, digest in [_checked_digest(name)]
    }
