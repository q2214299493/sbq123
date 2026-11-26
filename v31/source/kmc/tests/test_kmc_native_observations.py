"""Synthetic versions of the explicit-lattice and gas-history records observed in serial 4.0."""
import pytest

from scripts.kinetic_parameters.export import zacros
from scripts.native_model import assemble
from scripts.surface_kmc.observations import check_lattice_output, history_frames
from test_kmc_spatial_core import open_model


def test_explicit_zero_vectors_and_gas_counts():
    data, config = open_model()
    _, manifest = assemble("zacros", data, config)
    mapping = manifest["validation"]
    walk = mapping["topology"]
    vectors = "0 0.0 0.0 0 0 0 0\n" * 2
    rows = []
    for i in range(1, 8):
        neighbors = [j for j in (i - 1, i + 1) if 1 <= j <= 7]
        rows.append(" ".join(map(str, [i, i, 0, 2 if i % 2 else 1, len(neighbors), *neighbors])))
    lattice = (vectors + "\n".join(rows)).encode()
    check_lattice_output(lattice, walk)
    with pytest.raises(ValueError, match="vectors"):
        check_lattice_output(lattice.replace(b"0 0.0", b"0 1.0", 1), walk)

    header = "Gas_Species: H2\nSurface_Species: HCu* HNi*\n"
    frame = "configuration 1 0 0.0 400.0 0.0\n" + "".join(f"{i} {i} 0 1\n" for i in range(1, 8))
    def frames(text):
        return list(history_frames(text.encode(), walk, mapping, data, zacros(data)["events"]))

    assert frames(header + frame + "0\n")[0]["gas_counts"] == {"H2-g": 0}
    with pytest.raises(ValueError, match="gas counts"):
        frames(header + frame)
    with pytest.raises(ValueError, match="gas species"):
        frames(header.replace("H2", "wrong") + frame + "0\n")
