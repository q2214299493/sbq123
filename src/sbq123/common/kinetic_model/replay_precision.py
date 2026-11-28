"""Numerical replay of rate coefficients; all scientific inputs retain exact identities."""
from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
from importlib.resources import files
import json
import math
import struct

from .contracts import identity


def _within_ulps(left, right):
    if (type(left) is not float or type(right) is not float or min(left, right) <= 0
            or not math.isfinite(left) or not math.isfinite(right)):
        return False
    # IEEE binary64 bit patterns are monotonic for positive numbers, including at binade boundaries.
    def bits(value):
        return struct.unpack(">Q", struct.pack(">d", value))[0]
    return abs(bits(left) - bits(right)) <= 4


def _split(document):
    shape = deepcopy(document)
    shape.pop("dataset_version")
    values = []
    for row in shape["reactions"]:
        for direction in ("forward", "reverse"):
            rate = row["rates"].get(direction)
            if isinstance(rate, dict) and "activity_coefficient_s^-1" in rate:
                values.append([row["reaction_id"], direction, rate.pop("activity_coefficient_s^-1")])
    return identity(shape), values


@lru_cache(maxsize=1)
def _originals():
    raw = files("sbq123.common").joinpath("resources/replay/derived-coefficients.json").read_bytes()
    if sha256(raw).hexdigest() != "59fcfaef75ee927d602cf3ae0b66e3440de7e0653f8816b97f128d7141d46838":
        raise ValueError("Changed immutable historical replay inventory")
    return json.loads(raw)


def original_representation(calculated):
    """Recover a byte-verified historical representation only after checking the live calculation."""
    if calculated.get("format") != "kinetic-dataset/1":
        return calculated
    shape, values = _split(calculated)
    original = _originals().get(shape)
    if original is None or calculated["dataset_version"] == original["dataset_version"]:
        return calculated
    reviewed = {(rid, direction): v for rid, direction, v in original["coefficients"]}
    for rid, direction, value in values:
        other = reviewed.get((rid, direction))
        if identity(value) != identity(other) and not _within_ulps(value, other):
            return calculated
    restored = deepcopy(calculated)
    for row in restored["reactions"]:
        for direction in ("forward", "reverse"):
            key = (row["reaction_id"], direction)
            if key in reviewed:
                row["rates"][direction]["activity_coefficient_s^-1"] = reviewed[key]
    version = identity({k: v for k, v in restored.items() if k != "dataset_version"})
    if version != original["dataset_version"]:
        raise ValueError("Reproduced record does not match the independently retained historical identity")
    restored["dataset_version"] = version
    return restored


def same_recalculation(original, calculated):
    """Compare an independently bound original to a derived record without relaxing its content hash."""
    for doc in (original, calculated):
        if doc["dataset_version"] != identity({k: v for k,v in doc.items() if k != "dataset_version"}):
            return False
    if original["dataset_version"] == calculated["dataset_version"]:
        return True
    left, x = _split(original)
    right, y = _split(calculated)
    pinned = _originals().get(left)
    if pinned and pinned["dataset_version"] != original["dataset_version"]:
        return False
    return (left == right and len(x) == len(y) and all(
        a[:2] == b[:2] and (identity(a[2]) == identity(b[2]) or _within_ulps(a[2], b[2]))
        for a, b in zip(x,y)))
