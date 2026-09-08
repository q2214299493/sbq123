from __future__ import annotations

from scripts.select_dual_model_ts_vasp_labels import select_samples


def _row(index: int, energy: float, disagreement: float, *, prefix: str = "pre") -> dict:
    return {
        "sample_id": f"{prefix}_{index:02d}",
        "image": f"{index:02d}",
        "structure_sha256": f"{index + (100 if prefix == 'fail' else 0):064x}",
        "primary_energy_eV": energy,
        "secondary_energy_eV": energy + 0.1,
        "movable_force_difference": {"vector_max_eV_per_A": disagreement},
        "reaction_coordinate_value_A": 3.0 - index * 0.1,
    }


def test_selection_includes_boundary_pair_ts_like_and_path_coverage() -> None:
    rows = [_row(index, -abs(index - 8), index / 100) for index in range(17)]
    rows.append(_row(12, -3.9, 0.5, prefix="fail"))
    selected = select_samples(
        rows,
        boundary_pairs=[
            {
                "image": "12",
                "last_geometry_valid_sample": "pre_12",
                "first_geometry_valid_failure_sample": "fail_12",
                "reaction_coordinate_before_A": 1.16,
                "reaction_coordinate_after_A": 1.09,
            }
        ],
        minimum=5,
        maximum=7,
    )
    by_sample = {row["sample_id"]: row for row in selected}
    assert {"pre_08", "pre_12", "fail_12"} <= set(by_sample)
    assert by_sample["pre_08"]["role"] == "ts_like"
    assert by_sample["pre_12"]["role"] == "last_geometry_valid_point"
    assert by_sample["fail_12"]["role"] == "first_geometry_valid_failure_point"
    assert any(row["role"] == "rising_path" for row in selected)
    assert all(row["candidate_score"]["composite_rank_score"] >= 0 for row in selected)


def test_real_committee_disagreement_replaces_external_auditor_for_priority() -> None:
    rows = [_row(index, -abs(index - 8), 0.01) for index in range(17)]
    committee = {
        row["sample_id"]: {
            "force_disagreement_eV_per_A": 1.0 if row["sample_id"] == "pre_06" else 0.1,
            "relative_energy_disagreement_eV": 0.2,
        }
        for row in rows[1:-1]
    }
    selected = select_samples(
        rows,
        boundary_pairs=[],
        minimum=5,
        maximum=7,
        committee_rows=committee,
    )
    selected_by_id = {row["sample_id"]: row for row in selected}
    assert "maximum_MatRIS_committee_disagreement" in selected_by_id["pre_06"]["reasons"]
