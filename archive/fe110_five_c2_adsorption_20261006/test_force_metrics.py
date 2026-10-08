import numpy as np
import pytest

from archive.fe110_five_c2_adsorption_20261006.assess_c2_force_prediction import metrics


def test_vector_and_component_metrics_are_distinct():
    result = metrics(np.array([[3.0, 4.0, 0.0], [0.0, 0.0, 0.0]]))
    assert result["component_mae_eV_per_A"] == pytest.approx(7 / 6)
    assert result["vector_rmse_eV_per_A"] == pytest.approx(np.sqrt(12.5))
    assert result["vector_p95_eV_per_A"] == pytest.approx(4.75)
    assert result["vector_max_eV_per_A"] == 5
