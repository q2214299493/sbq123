from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def expand_symbols(symbols: Sequence[str], counts: Sequence[int]) -> list[str]:
    """Expand grouped element symbols into one symbol per atom."""
    if len(symbols) != len(counts):
        raise ValueError("symbols and counts must have equal length")
    return [symbol for symbol, count in zip(symbols, counts, strict=True) for _ in range(int(count))]


def minimum_image_delta_xy(delta_fractional: np.ndarray) -> np.ndarray:
    """Wrap a fractional displacement along periodic slab x/y axes only."""
    result = np.asarray(delta_fractional, dtype=float).copy()
    result[..., :2] -= np.round(result[..., :2])
    return result


def minimum_image_delta_xyz(delta_fractional: np.ndarray) -> np.ndarray:
    """Wrap a fractional displacement along all three periodic axes."""
    result = np.asarray(delta_fractional, dtype=float).copy()
    return result - np.round(result)


def pbc_xy_vector(cell: np.ndarray, first_cartesian: np.ndarray, second_cartesian: np.ndarray) -> np.ndarray:
    """Return first-minus-second Cartesian displacement under slab x/y PBC."""
    delta = (np.asarray(first_cartesian) - np.asarray(second_cartesian)) @ np.linalg.inv(cell)
    return minimum_image_delta_xy(delta) @ cell


def pbc_xy_distance(cell: np.ndarray, first_cartesian: np.ndarray, second_cartesian: np.ndarray) -> float:
    """Return Cartesian distance under slab x/y PBC, in the cell's length unit."""
    return float(np.linalg.norm(pbc_xy_vector(cell, first_cartesian, second_cartesian)))


def inplane_pbc_vector(cell: np.ndarray, first_cartesian: np.ndarray, second_cartesian: np.ndarray) -> np.ndarray:
    """Return the lateral part of a slab-PBC displacement."""
    vector = pbc_xy_vector(cell, first_cartesian, second_cartesian)
    vector[..., 2] = 0.0
    return vector


def relative_positions_xy(cell: np.ndarray, positions: np.ndarray, anchor: np.ndarray) -> np.ndarray:
    """Return positions relative to an anchor with slab x/y minimum images."""
    fractional = (np.asarray(positions) - np.asarray(anchor)) @ np.linalg.inv(cell)
    return minimum_image_delta_xy(fractional) @ cell
