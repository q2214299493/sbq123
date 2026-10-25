import pytest

from archive.fe110_grouped_supplement_20261025.analyze import choose, complete_link_groups


def item(name, graph="g", comp="C2H3", persistent=1, ratio=.2):
    return {"sample_id": name, "partition": "train", "composition": comp,
        "graph_signature": graph, "robust_missing_frames_all_scales": persistent,
        "novelty_ratio": ratio, "adsorbate_component_count": 1}


def test_complete_link_prevents_transitive_chaining():
    points = [item("a"), item("b"), item("c")]
    distances = {frozenset(("a", "b")): .6, frozenset(("b", "c")): .6,
                 frozenset(("a", "c")): 1.2}
    result = complete_link_groups(points, lambda a, b: distances[frozenset((a["sample_id"], b["sample_id"]))])
    assert [[r["sample_id"] for r in g] for g in result] == [["a", "b"], ["c"]]
    assert result == complete_link_groups(list(reversed(points)),
        lambda a, b: distances[frozenset((a["sample_id"], b["sample_id"]))])


def test_never_merge_different_graphs_or_compositions():
    points = [item("a"), item("b", graph="other"), item("c", comp="C3H2O")]
    assert len(complete_link_groups(points, lambda a, b: 0)) == 3


def test_reserved_partition_rejected_before_distance():
    point = {**item("a"), "partition": "final_test"}
    with pytest.raises(ValueError, match="only training"):
        complete_link_groups([point], lambda a, b: 0)


def test_persistent_connected_priority_and_force_unknown():
    a, b = item("a", persistent=0, ratio=.8), item("b", ratio=.2)
    chosen, action = choose([a, b], lambda a, b: 0)
    assert chosen is b and action == "ROUND1_CONNECTED_PERSISTENT"


def test_fragment_outlier_reserve_and_other_types_deferred():
    point = {**item("a", ratio=1.3), "adsorbate_component_count": 4}
    assert choose([point], lambda a, b: 0)[1] == "RESERVE_SOAP_OUTLIER"
    assert choose([item("a", persistent=0)], lambda a, b: 0)[1] == "DEFER_NO_FORCE_ERROR_EVIDENCE"
