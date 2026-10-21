from archive.fe110_c2_06_10_table_sync_20261022.prepare import presentation


def source(name, converged=True, reclassified=False):
    return {"name": name, "target_graph": "[CH2][C][O]", "technical_convergence": converged,
            "ionic_steps": 300, "fmax_eV_A": .470608, "eligible_reclassified_review": reclassified}


def test_duplicate_coadsorption_not_counted_as_new_target():
    identity, status, note = presentation(source("09_B", reclassified=True), ["CH2", "CO"])
    assert identity == "CH2* + CO*"
    assert "重复" in status and "07_A" in note


def test_unconverged_snapshot_never_presented_as_stable():
    _, status, note = presentation(source("07_C", converged=False), ["C2H2O"])
    assert "不作稳定态" in status and "0.470608" in note


def test_borderline_pair_kept_without_acceptance_claim():
    _, status, note = presentation(source("08_B"), ["C2H2O"])
    assert "待正式接受" in status and "暂不合并" in note
