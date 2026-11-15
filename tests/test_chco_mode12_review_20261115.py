"""Bounded full-mode parsing tests;no VASP/GPU/model execution."""
import numpy as np
import pytest

from archive.chco_mode12_20261115.review import full_mode


HEADER = "Eigenvectors and eigenvalues of the dynamical matrix\n"
FREQUENCY = "12 f/i= 9.0 THz 56.0 2PiTHz 318.644011 cm-1 39.0 meV\n"


def test_full_rows_preserve_reference_and_vectors():
    text = HEADER + FREQUENCY + "X Y Z dx dy dz\n0 1 2 .3 -.4 .5\n3 4 5 -.3 .4 -.5\n"
    positions, vectors, header = full_mode(text, 12, 2)
    assert np.array_equal(positions, [[0, 1, 2], [3, 4, 5]])
    assert np.array_equal(vectors, [[.3, -.4, .5], [-.3, .4, -.5]])
    assert header == HEADER.strip()


@pytest.mark.parametrize("rows", ["0 1 2 .3 -.4 .5\n", "0 1 2 nan 0 0\n3 4 5 0 0 0\n"])
def test_incomplete_or_nonfinite_modes_rejected(rows):
    with pytest.raises(ValueError, match="Incomplete or nonfinite"):
        full_mode(HEADER + FREQUENCY + rows, 12, 2)


def test_duplicate_representation_is_not_silently_mass_corrected_twice():
    with pytest.raises(ValueError, match="one native mode block"):
        full_mode(HEADER + FREQUENCY + FREQUENCY, 12, 1)


def test_unrecognized_mode_basis_rejected():
    with pytest.raises(ValueError, match="Unknown eigenvector"):
        full_mode("Eigenvectors after division by SQRT(mass)\n" + FREQUENCY + "0 0 0 1 0 0\n", 12, 1)
