from __future__ import annotations

import math
import shutil
import subprocess
import sys
from pathlib import Path

from scripts.mlip_same_structure_benchmark import (
    composition_key,
    force_metrics,
    kendall_tau,
    percentile,
    spearman,
)


def test_force_metrics_use_only_declared_movable_atoms() -> None:
    labels = [[[100.0, 100.0, 100.0], [1.0, 2.0, 3.0]]]
    predictions = [[[0.0, 0.0, 0.0], [2.0, 4.0, 6.0]]]

    metrics = force_metrics(labels, predictions, [[1]])

    assert metrics["movable_atom_count"] == 1
    assert math.isclose(metrics["component_mae_eV_per_A"], 2.0)
    assert math.isclose(metrics["component_rmse_eV_per_A"], math.sqrt(14.0 / 3.0))
    assert math.isclose(metrics["vector_rmse_eV_per_A"], math.sqrt(14.0))
    assert math.isclose(metrics["vector_p95_eV_per_A"], math.sqrt(14.0))
    assert math.isclose(metrics["vector_max_eV_per_A"], math.sqrt(14.0))


def test_rank_metrics_and_percentile() -> None:
    assert spearman([0.0, 1.0, 2.0], [0.0, 2.0, 1.0]) == 0.5
    assert kendall_tau([0.0, 1.0, 2.0], [0.0, 2.0, 1.0]) == 1.0 / 3.0
    assert percentile([0.0, 10.0], 0.95) == 9.5


def test_composition_key_is_order_independent() -> None:
    assert composition_key(["Fe", "H", "Fe", "C"]) == "C1-Fe2-H1"
    assert composition_key(["C", "Fe", "Fe", "H"]) == "C1-Fe2-H1"


def test_standalone_prediction_bundle_imports_without_repository(tmp_path: Path) -> None:
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    for name in ("artifact_io.py", "mlip_same_structure_benchmark.py", "dual_model_ts_force_prediction_batch.py"):
        shutil.copyfile(scripts / name, tmp_path / name)
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "from mlip_same_structure_benchmark import sha256_file, load_json; "
        "from dual_model_ts_force_prediction_batch import _sha256; "
        "assert _sha256('a'*64, label='test') == 'a'*64"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", code, str(tmp_path)],
        cwd=tmp_path, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
