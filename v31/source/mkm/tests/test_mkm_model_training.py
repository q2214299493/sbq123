"""Synthetic held-out model comparisons and independent coefficient covariance."""

from copy import deepcopy

import numpy as np
import pytest

from scripts.artifact_io import sha256_file, sha256_json
from scripts.kinetic_parameters.prediction import validate_fit
from scripts.kinetic_parameters.training import publish_evidence, train
from test_kinetic_parameters import DIGEST, case
from test_mkm_energy_prediction import binding, fit_for, run, version


def request():
    n, _ = case()
    ref = fit_for(n, "bep", ["reaction_energy"], [0.6, 0.2])
    context = {k: ref[k] for k in ("scope", "energy_basis", "reference_id", "standard_state_id", "standard_states_sha256")}
    axes = {"reaction_energy": DIGEST, "z": DIGEST, "x": DIGEST}
    target = "forward_barrier"
    digest = sha256_json(dict(context, target=target, descriptor_definitions=axes))

    def row(i, x, perturbation):
        return dict(
            sample_id=str(i),
            context_sha256=digest,
            source_sha256=sha256_json(["synthetic", i]),
            descriptors_eV=dict(reaction_energy=x, x=x, z=x * x),
            target_eV=0.6 + 0.2 * x + perturbation,
        )

    return dict(
        context=context,
        target=target,
        descriptor_definitions=axes,
        training=[row(i, i - 2, e * 0.01) for i, e in enumerate([1, -2, 2, -2, 1])],
        validation=[row(5, -0.5, 0), row(6, 0.5, 0)],
        candidates=[
            dict(model_id="linear", kind="bep", axes=["reaction_energy"]),
            dict(model_id="alternative", kind="descriptor_barrier", axes=["z"]),
        ],
    )


def test_holdout_and_coefficient_covariance():
    spec = request()
    result = train(spec)
    assert result["recommendation"] == "linear" and result["review_required"]
    best = result["candidates"][0]
    fit = best["fit"]
    assert "approval" not in fit and fit["coefficients"] == pytest.approx([0.6, 0.2])
    assert best["evidence"]["held_out_rmse_eV"] == pytest.approx(0.0, abs=1e-14)
    var = 0.0014 / 3
    np.testing.assert_allclose(fit["covariance"], np.diag([var / 5, var / 10]), atol=1e-16)
    assert fit["residual_sigma_eV"] ** 2 == pytest.approx(var)
    assert fit["model_version"] == version(deepcopy(fit))["model_version"]
    validate_fit(
        version(deepcopy(fit)), {DIGEST, sha256_json(best["evidence"]), sha256_json(spec["training"]), sha256_json(spec["validation"])}
    )


def test_relabelled_observation_and_case_leakage():
    spec = request()
    spec["validation"][0] = dict(spec["training"][0], sample_id="renamed")
    with pytest.raises(ValueError, match="observation"):
        train(spec)
    spec = request()
    spec["training"][0]["case_id"] = spec["validation"][0]["case_id"] = "same-structure"
    with pytest.raises(ValueError, match="Case"):
        train(spec)


def test_disjoint_observations_in_one_publication_and_external_evaluation():
    spec = request()
    for row in spec["training"] + spec["validation"]:
        row.update(observation_sha256=row["source_sha256"], source_sha256=DIGEST, case_id=row["sample_id"])
    spec["evaluation"] = [dict(spec["validation"][0], sample_id="external", case_id="independent",
                               observation_sha256=sha256_json(["new observation"]), target_eV=1.5)]
    chosen = train(spec)
    assert chosen["recommendation"] == "linear"
    assert chosen["candidates"][0]["evidence"]["metric_role"] == "model_selection_validation"
    assert chosen["independent_evaluation"]["rmse_eV"] == pytest.approx(1.)
    assert train(request())["independent_evaluation"] is None
    spec["evaluation"][0]["observation_sha256"] = spec["validation"][0]["observation_sha256"]
    with pytest.raises(ValueError, match="observation"):
        train(spec)
    del spec["evaluation"]
    del spec["validation"][0]["observation_sha256"]
    with pytest.raises(ValueError, match="Shared source"):
        train(spec)


def test_joint_hull_and_ambiguous_selection():
    spec = request()
    spec["candidates"] = [dict(model_id="joint", kind="descriptor_barrier", axes=["x", "z"])]
    spec["validation"][0]["descriptors_eV"].update(x=1.9, z=0.2)
    spec["validation"][1]["descriptors_eV"]["z"] = 1.0
    result = train(spec)
    assert result["recommendation"] is None
    assert result["candidates"][0]["evidence"]["outside_domain"] == ["5"]
    spec = request()
    spec["candidates"][1] = dict(spec["candidates"][0], model_id="second")
    assert train(spec)["recommendation"] is None


@pytest.mark.parametrize("defect,match", [("leak", "distinct"), ("units", "context"), ("rank", "independent"), ("source", "SHA-256")])
def test_unusable_training_evidence(defect, match):
    spec = request()
    if defect == "leak":
        spec["validation"][0]["sample_id"] = spec["training"][0]["sample_id"]
    elif defect == "units":
        spec["validation"][0]["context_sha256"] = "0" * 64
    elif defect == "source":
        spec["validation"][0]["source_sha256"] = "missing"
    else:
        for row in spec["training"]:
            row["descriptors_eV"]["reaction_energy"] = 1.0
    with pytest.raises(ValueError, match=match):
        train(spec)


def test_two_bep_calibrations_share_validation():
    spec = request()
    spec["candidates"][1] = dict(spec["candidates"][0], model_id="subset", training_ids=["0", "2", "4"])
    comparison = train(spec)
    full, subset = [row["fit"] for row in comparison["candidates"]]
    assert comparison["recommendation"] == "linear"
    assert full["validation_sha256"] == subset["validation_sha256"]
    assert full["training_sha256"] != subset["training_sha256"]


def test_unsigned_training_to_reviewed_prediction(tmp_path):
    spec = request()
    comp = train(spec)
    publish_evidence(tmp_path, spec, comp)
    fit = comp["candidates"][0]["fit"]
    n, m = case()
    for key in ("training_sha256", "validation_sha256", "fit_source_sha256"):
        digest = fit[key]
        path = tmp_path / (digest + ".json")
        assert sha256_file(path) == digest
        n["source_artifacts"].append(dict(role="verified_evidence", sha256=digest, file=path.name))
        m["sources"].append(dict(kind="synthetic", sha256=digest, reference=path.name))
    n["network_version"] = sha256_json({k: v for k, v in n.items() if k != "network_version"})
    prediction = binding(n)
    prediction["models"] = [version(deepcopy(fit))]
    tr = run(n, m, prediction)["reactions"][0]["prediction"]
    assert tr["gibbs_eV"] == pytest.approx(dict(reaction=-0.1, forward=0.58, reverse=0.68))
    variance = 0.0014 / 3
    expected = variance * (1 + 1 / 5 + 0.1**2 / 10) + 0.2**2 * 0.04
    assert tr["covariance_eV2"][1][1] == pytest.approx(expected)
