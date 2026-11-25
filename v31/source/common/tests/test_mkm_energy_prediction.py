"""Synthetic calibrations only. Never execute a native engine or write archive files."""
import json
import math
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
from jsonschema import ValidationError

from scripts.artifact_io import sha256_file, sha256_json
from scripts.baseline_mkm.single_point import qualify
from scripts.kinetic_parameters.engine import generate, qualify_network_rows
from scripts.kinetic_parameters.export import catkinas, zacros
from scripts.kinetic_parameters.prediction import validator
from scripts.reaction_network.builder import build_network
from scripts.thermochemistry.harmonic import KB
from test_kinetic_parameters import DIGEST, case, signed

ARCHIVE = Path(__file__).resolve().parents[1] / "archive/v221_catkinas/nicu-v221-400k-001"


def observation(key, value, unit="eV"):
    return dict(id=key, value=value, unit=unit, definition_sha256=DIGEST, source_sha256=DIGEST)


def version(fit):
    fit["model_version"] = sha256_json({k: v for k, v in fit.items() if k not in ("approval", "model_version")})
    fit["approval"] = dict(status="validated", reviewer="synthetic reviewer", reviewed_at="2026-01-01T00:00:00Z",
                           subject_sha256=fit["model_version"])
    return fit


def fit_for(n, kind, axes, coefficients, rid="ads", family=None):
    r = next(e["definition"] for e in n["reactions"] if e["definition"]["reaction_id"] == rid)
    sites = set().union(*(r[k] or {} for k in ("required_sites", "sites_consumed", "sites_released")))
    species = {s["species_id"]: s for s in n["species"]}
    for s in r["reactants"].keys() | r["products"].keys():
        sites.update(species[s].get("site_occupancy") or {})
    scope = dict(project_id=n["project_id"], reaction_id=None if family else rid, family_id=family, phase_ids=r["phase_ids"],
                 surface_ids=r["surface_ids"], interface_id=r["interface_id"], site_ids=sorted(sites),
                 temperature_K=[300, 600], pressure_Pa=[0, 1e7])
    return version(dict(model_id=f"{kind}-{family or rid}", kind=kind, scope=scope, energy_basis="gibbs",
                        reference_id=r["energy_reference_id"], standard_state_id="demo-standard",
                        standard_states_sha256=sha256_json(n["parameter_sets"][0]["standard_states"]),
                        axes=[dict(id=k, definition_sha256=DIGEST) for k in axes], bounds_eV=[[-1, 1] for _ in axes],
                        halfspaces=[], coefficients=coefficients, covariance=np.zeros((len(axes)+1, len(axes)+1)).tolist(),
                        residual_sigma_eV=0., fit_source_sha256=DIGEST, training_sha256=DIGEST, validation_sha256=DIGEST))


def binding(n, rid="ads", family=None):
    fit = fit_for(n, "bep", ["reaction_energy"], [.6, .5], rid, family)
    row = next(r for r in n["reactions"] if r["definition"]["reaction_id"] == rid)
    d = row["energies"]["gibbs_ev"]["reaction"]
    return dict(format="mkm-energy-prediction/1", energy_basis="gibbs", family_id=family,
                reaction_axis_sha256=DIGEST, reaction_source="observation", observations=[observation("reaction_energy", d)],
                observation_covariance=[[.04]], models=[fit], cross_covariances=[], gibbs_bridge=None,
                **({"family_evidence_sha256": DIGEST} if family else {}))


def run(n, m, spec):
    return generate(n, signed(n, dict(m, energy_prediction=spec)))


def test_single_bep_independent_reference_and_qualification():
    n, m = case()
    spec = binding(n)
    f = spec["models"][0]
    f.update(covariance=[[.01, .002], [.002, .04]], residual_sigma_eV=.03)
    version(f)
    data = run(n, m, spec)
    row = data["reactions"][0]
    tr = row["prediction"]
    assert data["export_eligible"] and not data["execution_authorized"] and not row["scientifically_validated"]
    assert tr["gibbs_eV"] == pytest.approx(dict(reaction=-.1, forward=.55, reverse=.65))
    # Var(f)=.01+(-.1)^2*.04+2*(-.1)*.002+.5^2*.04+.03^2
    vf = .0209
    assert tr["covariance_eV2"][1] == pytest.approx([.02, vf, vf-.02])
    assert tr["sigma_eV"]["reverse"] == pytest.approx(math.sqrt(vf+.04-2*.02))
    rates = row["rates"]
    assert rates["reverse"]["sigma_ln_k"] == pytest.approx(math.sqrt(.0209)/(KB*400))
    assert math.log(rates["forward"]["activity_coefficient_s^-1"]/rates["reverse"]["activity_coefficient_s^-1"]) == pytest.approx(.1/(KB*400))
    assert row["equilibrium"]["log_ratio_residual"] == pytest.approx(0, abs=1e-12)
    assert catkinas(data)["rows"][0]["provenance"]["energy_prediction"] == tr
    validator("_result").validate(tr)
    with pytest.raises(ValueError, match="lattice-event"):
        zacros(data)
    bindings = signed(n, dict(m, energy_prediction=spec))
    rows, replay = qualify_network_rows(n, bindings, conservation={"ads": {"unresolved": []}})
    assert rows["ads"]["status"] == "qualified" and replay == data


def descriptors(n, spec):
    spec.update(reaction_source="descriptor", observations=[observation("Y", 100, "meV"), observation("X", .2)],
                observation_covariance=[[100., .002], [.002, .0004]])
    reaction = fit_for(n, "descriptor_reaction", ["X", "Y"], [-.4, 1., 1.])
    reaction["halfspaces"] = [dict(normal=[1., 2.], upper_eV=.5)]
    spec["models"].insert(0, version(reaction))


def test_ordered_chain_and_cross_covariance():
    n, m = case()
    spec = binding(n)
    descriptors(n, spec)
    tr = run(n, m, spec)["reactions"][0]["prediction"]
    assert tr["selected"][0]["axis_values_eV"] == pytest.approx([.2, .1])
    assert tr["selected"][1]["output_eV"] == pytest.approx(.55)
    assert tr["covariance_eV2"][0][0] == pytest.approx(.0004+.0001+2*.000002)
    # First-stage intercept and second-stage intercept estimated from shared data.
    for f in spec["models"]:
        f["covariance"][0][0] = .01
        version(f)
    a, b = [f["model_version"] for f in spec["models"]]
    spec["cross_covariances"] = [dict(left=a+":b0", right=b+":b0", value=.005)]
    tr = run(n, m, spec)["reactions"][0]["prediction"]
    assert tr["covariance_eV2"][1][1] == pytest.approx(.5**2*(.000504+.01)+.01+2*.5*.005)
    spec["observations"][0]["value"] = 300  # inside both univariate bounds
    with pytest.raises(ValueError, match="extrapolation"):
        run(n, m, spec)


def test_direct_barrier_distinct_from_bep_and_units():
    n, m = case()
    spec = binding(n)
    spec["models"] = [fit_for(n, "descriptor_barrier", ["CO"], [.5, 2.])]
    spec["observations"].append(observation("CO", 9.648533212331, "kJ/mol"))
    spec["observation_covariance"] = [[.04, 0], [0, 0]]
    tr = run(n, m, spec)["reactions"][0]["prediction"]
    assert tr["gibbs_eV"]["forward"] == pytest.approx(.7)
    assert tr["gibbs_eV"]["reverse"] == pytest.approx(.8)
    spec["models"].append(binding(n)["models"][0])
    with pytest.raises(ValueError, match="conflict"):
        run(n, m, spec)


def test_reaction_scope_vs_family_and_out_of_domain_candidates():
    n, m = case()
    spec = binding(n, family="H-transfer")
    second = fit_for(n, "bep", ["reaction_energy"], [.8, .2])
    spec["models"].append(second)
    with pytest.raises(ValueError, match="found 2"):
        run(n, m, spec)
    second["bounds_eV"] = [[0, 1]]
    version(second)
    tr = run(n, m, spec)["reactions"][0]["prediction"]
    assert [v["outcome"] for v in tr["candidate_decisions"]] == ["selected", "outside_domain"]
    spec["family_id"] = "not-reviewed-for-this-fit"
    with pytest.raises(ValueError, match="found 0"):
        run(n, m, spec)


@pytest.mark.parametrize("field,value", [("phase_ids", ["wrong"]), ("surface_ids", []), ("interface_id", "elsewhere"),
                                         ("site_ids", ["other"]), ("temperature_K", [500, 600]), ("pressure_Pa", [0, 1])])
def test_catalyst_and_condition_scope(field, value):
    n, m = case()
    spec = binding(n)
    fit = spec["models"][0]
    fit["scope"][field] = value
    version(fit)
    with pytest.raises(ValueError, match="found 0"):
        run(n, m, spec)


@pytest.mark.parametrize("change,match", [("version", "version"), ("fit_source", "Unverified"),
    ("observation", "unverified"), ("negative", "Negative"), ("covariance", "semidefinite"),
    ("duplicate", "Duplicate"), ("convention", "found 0"), ("duplicate_gibbs", "Gibbs"),
    ("coverage", "duplicate corrections"), ("review", "Stale"), ("standard_states", "found 0")])
def test_rejections(change, match):
    n, m = case()
    spec = binding(n)
    fit = spec["models"][0]
    if change == "version":
        fit["coefficients"][0] += .01
    elif change == "fit_source":
        fit["training_sha256"] = "a"*64
        version(fit)
    elif change == "observation":
        spec["observations"][0]["source_sha256"] = "a"*64
    elif change == "negative":
        fit["coefficients"][0] = -1
        version(fit)
    elif change == "covariance":
        fit["covariance"] = [[1, 2], [2, 1]]
        version(fit)
    elif change == "duplicate":
        spec["models"].append(deepcopy(fit))
    elif change == "convention":
        fit["reference_id"] = "different"
        version(fit)
    elif change == "duplicate_gibbs":
        spec["gibbs_bridge"] = bridge(fit, "enthalpy")
    elif change == "coverage":
        m["coverage_fractions"] = {"test": .2}
    elif change == "review":
        fit["approval"]["subject_sha256"] = "0"*64
    elif change == "standard_states":
        fit["standard_states_sha256"] = sha256_json({"gas_pressure_Pa": 1.})
        version(fit)
    with pytest.raises(ValueError, match=match):
        run(n, m, spec)


def bridge(fit, basis):
    return dict(from_basis=basis, to_basis="gibbs", reaction_eV=.02, forward_eV=.03, covariance_eV2=[[.01, 0], [0, .02]],
                source_sha256=DIGEST, temperature_K=400, standard_state_id=fit["standard_state_id"], reference_id=fit["reference_id"])


@pytest.mark.parametrize("basis", ["electronic", "enthalpy"])
def test_non_gibbs_predictions_need_a_bound_bridge(basis):
    n, m = case()
    spec = binding(n)
    fit = spec["models"][0]
    fit["energy_basis"] = spec["energy_basis"] = basis
    version(fit)
    if basis == "electronic":
        spec["observations"][0]["value"] = n["reactions"][0]["energies"]["electronic_ev"]["reaction"]
    with pytest.raises(ValueError, match="Gibbs bridge"):
        run(n, m, spec)
    spec["gibbs_bridge"] = bridge(fit, basis)
    tr = run(n, m, spec)["reactions"][0]["prediction"]
    raw = tr["basis_energies_eV"]
    assert tr["gibbs_eV"] == pytest.approx(dict(forward=raw["forward"]+.03, reverse=raw["reverse"]+.01, reaction=raw["reaction"]+.02))
    spec["gibbs_bridge"]["temperature_K"] = 410
    with pytest.raises(ValueError, match="Gibbs bridge"):
        run(n, m, spec)


def test_fixed_and_two_distinct_families_reproduce_native_inputs_offline():
    n, archived, config = (json.loads((ARCHIVE/f"{key}.json").read_bytes()) for key in ("network", "dataset", "configuration"))
    fixed_files, _ = qualify(n, archived, config)
    assert fixed_files["INPUT_phase25.m"].encode() == (ARCHIVE/"input/INPUT_phase25.m").read_bytes()
    models = [deepcopy(row["model"]) for row in archived["reactions"]]
    definitions = [binding(n, "transfer", "transfer-family"), binding(n, "hydrogenate", "addition-family")]
    fits = [d["models"][0] for d in definitions]
    fits[1]["coefficients"] = [.8, .3]
    version(fits[1])
    for rid, spec in zip(("transfer", "hydrogenate"), definitions, strict=True):
        model = next(m for m in models if m["reaction_id"] == rid)
        spec["models"] = deepcopy(fits)
        model.pop("scientific_review")
        model["energy_prediction"] = spec
        model.update(signed(n, model)["models"][0])
    data = generate(n, dict(network_version=n["network_version"], models=models))
    assert data["export_eligible"]
    assert [r["prediction"]["selected"][0]["model_id"] for r in data["reactions"] if "prediction" in r] == [f["model_id"] for f in fits]
    assert [r for r in data["reactions"] if "prediction" not in r] == [r for r in archived["reactions"] if r["reaction_id"] in ("ads", "desorb")]
    files, manifest = qualify(n, data, dict(config, dataset_version=data["dataset_version"]))
    assert not manifest["execution_authorized"]
    assert files != fixed_files and "BEPMode" not in files["INPUT_phase25.m"]
    assert "BarrierMode = -2;" in files["INPUT_phase25.m"]
    data["reactions"][1]["prediction"]["sigma_eV"]["reaction"] += 1
    data["dataset_version"] = sha256_json({k: v for k, v in data.items() if k != "dataset_version"})
    with pytest.raises(ValueError, match="Dataset differs"):
        qualify(n, data, config)


def test_closed_schema_and_outer_review():
    n, m = case()
    spec = binding(n)
    spec["native_BEPMode"] = 1
    with pytest.raises(ValidationError):
        run(n, m, spec)
    del spec["native_BEPMode"]
    b = signed(n, dict(m, energy_prediction=spec))
    b["models"][0]["energy_prediction"]["family_id"] = "new assignment"
    with pytest.raises(ValueError, match="Stale kinetic model review"):
        generate(n, b)


def test_structurally_reviewed_network_without_ts_or_registered_rate_barriers():
    parent, m = case()
    reaction = deepcopy(parent["reactions"][0]["definition"])
    reaction.update(free_energies=None, electronic_energies=None, ts_treatment=None, ts_id=None)
    definition = dict(parent["catalog"], format="network-definition/1", reactions=[reaction],
                      species=parent["species"], parameter_sets=[])
    opts = dict(verified_hashes={DIGEST}, sources=parent["source_artifacts"])
    draft = build_network(definition, **opts)
    decision = dict(parent["reactions"][0]["network_review"],
                    subject_sha256=draft["reactions"][0]["subject_sha256"])
    n = build_network(definition, decisions=[decision], **opts)
    assert n["reactions"][0]["level"] == "STRUCTURALLY_VALID"
    m["parameter_input"] = dict(parent["parameter_sets"][0], forward=None, reverse=None, eligibility="draft")
    spec = binding(parent)
    descriptors(parent, spec)
    data = run(n, m, spec)
    r = data["reactions"][0]
    assert r["export_eligible"] and not r["scientifically_validated"]
    assert r["parameter_set"]["forward"] is None and r["prediction"]["provenance"] == "model_prediction"
    assert n["reactions"][0]["energies"]["gibbs_ev"]["forward"] is None
    assert catkinas(data)["rows"][0]["fixed_T_energy_input"]["BarrierMode"] == -2
    with pytest.raises(ValueError, match="independently reviewed"):
        run(draft, m, spec)


def test_missing_family_or_descriptor_evidence_and_ephemeral_sources():
    n, m = case()
    spec = binding(n, family="transfer")
    spec["family_evidence_sha256"] = "3"*64
    with pytest.raises(ValueError, match="family membership"):
        run(n, m, spec)
    spec["family_evidence_sha256"] = DIGEST
    m["sources"].append(dict(kind="model_prediction", sha256="3"*64, reference="synthetic descriptor source"))
    with pytest.raises(ValueError, match="bound to the network"):
        generate(n, signed(n, dict(m, energy_prediction=spec)), verified_hashes={"3"*64})


def test_cycle_consistency_after_mixing_predicted_and_fixed_rows():
    n, m = case()
    # Three independently identified reversible steps with a closed stoichiometric loop.
    # Exercise the dataset owner's closure gate directly with known scalar energies.
    from scripts.kinetic_parameters.engine import _dataset

    row = run(n, m, binding(n))["reactions"][0]
    records = []
    entries = []
    for i, (a, b, d) in enumerate([("A", "B", .1), ("B", "C", .2), ("C", "A", -.29)]):
        rid = f"r{i}"
        record = deepcopy(row)
        record["reaction_id"] = rid
        if i:
            del record["prediction"]
        record["energies"]["gibbs_ev"]["reaction"] = d
        record["energies"]["electronic_ev"]["reaction"] = None
        records.append(record)
        entries.append(dict(n["reactions"][0], definition=dict(n["reactions"][0]["definition"], reaction_id=rid),
                            net_stoichiometry={a: -1, b: 1}))
    with pytest.raises(ValueError, match="thermodynamic cycle"):
        _dataset(dict(n, reactions=entries), records)
    records[-1]["parameter_set"]["energy_reference_id"] = "incompatible-reference"
    with pytest.raises(ValueError, match="common energy reference"):
        _dataset(dict(n, reactions=entries), records)


def test_public_cli_with_distinct_content_bound_training_and_validation(tmp_path):
    root = Path(__file__).resolve().parents[1]
    folder = root / "tests/fixtures/mkm_energy_prediction"
    train = folder / "synthetic_training.json"
    holdout = folder / "synthetic_validation.json"
    training, validation = sha256_file(train), sha256_file(holdout)
    assert training != validation
    n, m = case()
    for path, digest in ((train, training), (holdout, validation)):
        n["source_artifacts"].append(dict(role="verified_evidence", sha256=digest, file=path.name))
        m["sources"].append(dict(kind="synthetic", reference=path.relative_to(root).as_posix(), sha256=digest))
    n["network_version"] = sha256_json({k: v for k, v in n.items() if k != "network_version"})
    spec = binding(n)
    fit = spec["models"][0]
    fit.update(training_sha256=training, validation_sha256=validation, fit_source_sha256=training,
               bounds_eV=[[-.2, .2]], axes=[dict(id="reaction_energy", definition_sha256=training)])
    version(fit)
    spec["reaction_axis_sha256"] = training
    spec["observations"][0].update(source_sha256=validation, definition_sha256=training)
    spec["observation_covariance"] = [[.02**2]]
    docs = {"network": n, "bindings": signed(n, dict(m, energy_prediction=spec))}
    for name, doc in docs.items():
        (tmp_path/f"{name}.json").write_text(json.dumps(doc), encoding="utf-8")
    cli = [sys.executable, "-B", "-m", "scripts.kinetic_parameters", str(tmp_path/"network.json"),
           "--models", str(tmp_path/"bindings.json")]
    for fmt in ("dataset", "catkinas"):
        subprocess.run([*cli, "--format", fmt, "--output", str(tmp_path/f"{fmt}.json")], cwd=root, check=True)
    result = json.loads((tmp_path/"dataset.json").read_bytes())["reactions"][0]["prediction"]
    oracle = json.loads(holdout.read_bytes())
    assert result["gibbs_eV"]["forward"] == pytest.approx(oracle["held_out_pair_eV"][1])
    assert result["gibbs_eV"]["reverse"] == pytest.approx(oracle["expected_reverse_barrier_eV"])
    native = json.loads((tmp_path/"catkinas.json").read_bytes())["rows"][0]
    assert native["provenance"]["energy_prediction"] == result


def test_axis_order_is_part_of_fit_and_observation_order_is_explicit():
    n, m = case()
    spec = binding(n)
    descriptors(n, spec)
    fit = spec["models"][0]
    fit["coefficients"] = [-.6, 2., 1.]
    version(fit)
    tr = run(n, m, spec)["reactions"][0]["prediction"]
    assert tr["basis_energies_eV"]["reaction"] == pytest.approx(-.1)
    spec["observations"].reverse()
    spec["observation_covariance"] = [r[::-1] for r in spec["observation_covariance"][::-1]]
    reordered = run(n, m, spec)["reactions"][0]["prediction"]
    assert reordered["gibbs_eV"] == tr["gibbs_eV"]
    np.testing.assert_allclose(reordered["covariance_eV2"], tr["covariance_eV2"])
    fit["axes"].reverse()
    with pytest.raises(ValueError, match="Stale"):
        run(n, m, spec)


def test_unavailable_alternative_descriptor_is_reported():
    n, m = case()
    spec = binding(n)
    other = fit_for(n, "descriptor_barrier", ["other"], [.4, .12])
    spec["models"].append(other)
    tr = run(n, m, spec)["reactions"][0]["prediction"]
    assert tr["candidate_decisions"][1]["outcome"] == "unavailable_axes"
    assert tr["gibbs_eV"]["forward"] == pytest.approx(.55)


def test_condition_family_fingerprints_fit_and_handles_missing_directional_templates():
    from scripts.baseline_mkm.condition_scan import family

    n, d, c = (json.loads((ARCHIVE/f"{key}.json").read_bytes()) for key in ("network", "dataset", "configuration"))
    row = d["reactions"][0]
    row["model"]["energy_prediction"] = binding(n)
    with_templates = family(n, d, c)
    row["parameter_set"].update(forward=None, reverse=None)
    without_templates = family(n, d, c)
    assert without_templates != with_templates
    fit = row["model"]["energy_prediction"]["models"][0]
    fit["coefficients"][1] += .01
    version(fit)
    assert family(n, d, c) != without_templates
