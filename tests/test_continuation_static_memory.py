import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('continuous_static_RAM', Path(__file__).resolve().parents[1] /
                                            'archive/chco_paper_aqcat25_20261112/continuation_static_memory.py')
memory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(memory)


def test_same_setup_measured_peak_leaves_reviewed_7GiB_headroom():
    assert memory.checked_peak_kB(4607844.0) == 4607844.0


@pytest.mark.parametrize('value', [0, -1, 6 * 1024**2, float('nan'), float('inf'), True])
def test_insufficient_or_invalid_measured_memory_cannot_reduce_allocation(value):
    with pytest.raises(ValueError):
        memory.checked_peak_kB(value)
