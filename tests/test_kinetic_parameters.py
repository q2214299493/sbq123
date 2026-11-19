"""Independent scalar references and end-to-end synthetic Phase 1/2.3 gates."""
import json
import math
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.artifact_io import sha256_file, sha256_json
from scripts.kinetic_parameters.engine import generate
from scripts.kinetic_parameters.export import catkinas, zacros
from scripts.kinetic_parameters.laws import activation_shift, coefficient, mean_field_rate, normalized_prefactor
from scripts.reaction_network.builder import build_network
from test_multiphase_contracts import reviewed_example

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests/fixtures/multiphase"
REF = FIX / "kinetic_reference.json"
ORACLE = json.loads(REF.read_bytes())
DIGEST = sha256_file(REF)
FE = ROOT / "reports/multiphase/networks/network-2a80b67c31201600a1858780bbe6c176b03f489fe24383441fca4f195b395483.json"


def bind_artifacts(value):
    if isinstance(value, dict):
        if "sha256" in value and "path" in value:
            value.update(path=REF.relative_to(ROOT).as_posix(), sha256=DIGEST)
        for item in value.values():
            bind_artifacts(item)
    if isinstance(value, list):
        for item in value:
            bind_artifacts(item)


def case(system="interface", temperature=400, barrier=0.4, gas=False, reversible=True, standard_pa=100000, without_parameters=False):
    d = json.loads((FIX / "valid.json").read_bytes())
    r, p = reviewed_example(d)
    if system != "interface":
        material = "Fe" if system == "Fe110" else "Al2O3"
        facet = system
        d["projects"][0].update(project_id=system, name="Synthetic kinetic benchmark")
        d["materials"] = [dict(d["materials"][0], project_id=system, material_id=material, name=material)]
        phase = dict(d["phases"][0], material_id=material, phase_id="solid",
                     name="synthetic bulk", composition={"Fe": 1} if system == "Fe110" else {"Al": 2, "O": 3})
        d["phases"] = [phase]
        d["surfaces"] = [dict(d["surfaces"][0], phase_id="solid", surface_id=facet,
                              miller_indices=[1, 1, 0] if system == "Fe110" else [0, 1, 2])]
        d["interfaces"] = []
        for site, label in zip(d["sites"], ("ledge", "pocket") if system == "Fe110" else ("acid", "basic-oxygen"), strict=True):
            site.update(surface_id=facet, site_type=label)
        for species in d["species"][1:]:
            species.update(material_ids=[material], surface_ids=[facet], interface_id=None)
        r.update(phase_ids=["solid"], surface_ids=[facet], interface_id=None, reaction_type="adsorption" if gas else "diffusion")
    if not gas:
        r.update(reactants={"H2-top": 1}, sites_consumed={"bridge-Cu": 1})
    if gas == "dissociative":
        r["products"] = {"H2-top": 1, "H2-bridge": 1}
        for s in d["species"][1:]:
            s["composition"] = {"H": 1}
        d["species"][1].update(site_occupancy={"bridge-Cu": 1}, surface_ids=["facet-Cu"], material_ids=["Cu"], interface_id=None)
    r["reversible"] = reversible
    if not reversible:
        p["reverse"] = None
    if reversible is None:
        d["format"] = "network-definition/1"
    r["free_energies"]["temperature_K"] = p["temperature_K"] = temperature
    p["standard_states"]["gas_pressure_Pa"] = standard_pa
    p["validity_range"].update(min_temperature_K=300, max_temperature_K=700)
    for name, b in (("forward", barrier), ("reverse", barrier + 0.1)):
        r["free_energies"]["values"][name]["value"] = b
        if p[name]:
            p[name]["activation_energy"]["value"] = b
    bind_artifacts(d)
    if without_parameters:
        d.update(format="network-definition/1", parameter_sets=[])
    ts = [{"grade": "A", "review_reference": "synthetic assignment", "assignment": "synthetic mode",
           "reaction_id": "ads", "structure_identity": r["ts_id"]}]
    opts = dict(ts_reviews=ts, verified_hashes={DIGEST}, sources=[{"role": "verified_evidence", "sha256": DIGEST, "file": REF.name}])
    n = build_network(d, **opts)
    decision = dict(subject_sha256=n["reactions"][0]["subject_sha256"], reaction_id="ads", decision="accepted",
                    reviewer="synthetic reviewer", reason="fixture only", reviewed_at="2026-11-19T01:00:00Z")
    n = build_network(d, **opts, decisions=[decision])
    model = {"reaction_id": "ads", "parameter_set_id": "params", "use_scope": "synthetic_benchmark", "standard_states": p["standard_states"],
             "forward": {"method": "tst", "kappa": 1}, "reverse": {"method": "tst", "kappa": 1} if reversible else None,
             "sources": [{"kind": "synthetic", "reference": REF.name, "sha256": DIGEST}],
             "local_event": {"site_ids": ["top-Ni", "bridge-Cu"], "initial": [None if gas else ["H2-top", 1], None],
                             "final": [["H2-bridge", 1], ["H2-bridge", 1]], "neighbors_zero_based": [[0, 1]],
                             "patterns_per_reference_site": {"forward": 2, "reverse": 2}}}
    if gas:
        model["forward"] = dict(method="gas_adsorption", gas_species_id="H2-g", mass_u=2, capture_area_m2=5e-20, sticking=0.25)
        model["reverse"] = {"method": "from_equilibrium"} if reversible else None
    if gas == "dissociative":
        model["forward"]["method"] = "dissociative_adsorption"
        model["local_event"]["final"] = [["H2-top", 1], ["H2-bridge", 2]]
    if without_parameters:
        model["parameter_input"] = dict(p, eligibility="draft", forward=None, reverse=None,
                                        validation={"status": "unreviewed", "review": None})
    return n, model


def signed(n, m):
    m = deepcopy(m)
    m["scientific_review"] = {"status": "validated", "reviewer": "synthetic analyst", "method": "fixture analytical comparison",
                              "reviewed_at": "2026-11-19T01:00:00Z", "subject_sha256": sha256_json([n["network_version"], m])}
    return {"network_version": n["network_version"], "models": [m]}


def dataset(n, m):
    return generate(n, signed(n, m), verified_hashes={DIGEST})


@pytest.mark.parametrize("system", ["Fe110", "oxide", "interface"])
def test_multiphase_tst_and_exports(system):
    n, m = case(system)
    data = dataset(n, m)
    r = data["reactions"][0]
    assert data["export_eligible"] and not data["execution_authorized"]
    k = r["rates"]["forward"]["activity_coefficient_s^-1"]
    assert k == pytest.approx(ORACLE["TST_s-1"]["400K_0.4eV"], rel=1e-12)
    assert k / r["rates"]["reverse"]["activity_coefficient_s^-1"] == pytest.approx(ORACLE["K_400K_minus0.1eV"])
    assert catkinas(data)["rows"][0]["forward"] == {"coefficient": k, "unit": "s^-1", "gas_partial_pressure_orders": {}}
    events = zacros(data)["events"]
    assert events[0]["pre_expon"] == k / 2 and events[0]["final"] == events[1]["initial"]


def test_independent_temperature_specific_free_energy():
    n, m = case(temperature=600, barrier=0.35)
    assert dataset(n, m)["reactions"][0]["rates"]["forward"]["activity_coefficient_s^-1"] == pytest.approx(ORACLE["TST_s-1"]["600K_0.35eV"])


def test_gas_collision_pressure_and_equilibrium_reverse():
    n, m = case(gas=True)
    data = dataset(n, m)
    r = data["reactions"][0]
    assert r["rates"]["forward"]["prefactor_at_unit_activity_s^-1"] == pytest.approx(ORACLE["collision_at_1bar_before_activation_s-1"])
    assert r["equilibrium"]["log_ratio_residual"] == pytest.approx(0, abs=1e-12)
    assert catkinas(data)["rows"][0]["forward"]["unit"] == "bar^-1 s^-1"
    event = zacros(data)["events"][0]
    assert event["unit"] == "bar^-1 s^-1" and event["gas_partial_pressure_orders"] == {"H2-g": 1}
    assert event["pre_expon"] == pytest.approx(catkinas(data)["rows"][0]["forward"]["coefficient"] / 2)


def test_dissociative_adsorption_is_first_order_in_gas_and_two_site():
    n, m = case(gas="dissociative")
    d = dataset(n, m)
    event = zacros(d)["events"][0]
    assert event["gas_partial_pressure_orders"] == {"H2-g": 1} and len(event["final"]) == 2
    assert d["reactions"][0]["rates"]["forward"]["activity_orders"]["vacant_sites"] == {"top-Ni": 1, "bridge-Cu": 1}
    m["forward"]["method"] = "gas_adsorption"
    with pytest.raises(ValueError, match="fragments"):
        dataset(n, m)


@pytest.mark.parametrize("reversible", [False, None])
def test_forward_only_respects_direction(reversible):
    n, m = case(reversible=reversible)
    d = dataset(n, m)
    assert d["reactions"][0]["rates"]["reverse"] is None
    assert d["reactions"][0]["rates"]["forward"] is not None
    assert d["export_eligible"] == (reversible is False)
    m["reverse"] = {"method": "from_equilibrium"}
    with pytest.raises(ValueError, match="confirmed reversibility"):
        dataset(n, m)


@pytest.mark.parametrize("kind", ["literature", "user_provided", "external_calculation", "local_calculation", "approved_assumption"])
def test_sourced_prefactor_separate_from_acceptance(kind):
    n, m = case()
    m.update(accepted_by="fixture owner", forward={"method": "prefactor"}, reverse={"method": "prefactor"})
    m["sources"][0]["kind"] = kind
    pending = generate(n, {"network_version": n["network_version"], "models": [m]})
    assert not pending["export_eligible"] and not pending["reactions"][0]["scientifically_validated"]
    assert dataset(n, m)["reactions"][0]["rates"]["forward"]["prefactor_at_unit_activity_s^-1"] == 1e12


def test_degeneracy_kappa_uncertainty_units_and_coverage():
    opts = dict(gas={}, product_gas={}, temperature=400, standard_pa=1e5, barrier=0.4, degeneracy=3,
                sigma={"quantity": "activation_free_energy", "unit": "eV", "value": 0.02, "method": "one_sigma"})
    rate = coefficient({"method": "tst", "kappa": 0.25}, None, **opts)
    assert rate["activity_coefficient_s^-1"] == pytest.approx(0.75 * ORACLE["TST_s-1"]["400K_0.4eV"])
    assert rate["sigma_ln_k"] == pytest.approx(0.58022591)
    assert normalized_prefactor(3, "Pa^-1 s^-1", 1, 2e5) == 6e5
    assert normalized_prefactor(3, "bar^-1 s^-1", 1, 2e5) == 6
    term = {"species_id": "x", "expression": "linear_transition_state_shift", "min_fraction": 0, "max_fraction": 0.8,
            "coefficient": {"value": 0.4, "unit": "eV", "reference_id": "ref"}, "already_in_barrier": False}
    assert activation_shift([term], {"x": 0.5}, "ref") == 0.2
    assert activation_shift([dict(term, already_in_barrier=True)], {"x": 0.5}, "ref") == 0
    with pytest.raises(ValueError, match="validity"):
        activation_shift([term], {"x": 0.9}, "ref")


@pytest.mark.parametrize("issue,match", [("gas_tst", "Gas capture"), ("mass", "mass"), ("normalization", "Reactor"),
                                         ("balance", "Detailed balance"), ("standard", "standard state"),
                                         ("graph", "Disconnected"), ("entity", "occupancy"), ("stale", "Stale")])
def test_reject_incompatible_parameters(issue, match):
    n, m = case(gas=issue in ("gas_tst", "sticking", "mass"))
    if issue == "gas_tst":
        m["forward"] = {"method": "tst", "kappa": 1}
    elif issue == "normalization":
        m["normalization"] = "mol kg^-1 s^-1"
    elif issue == "mass":
        m["forward"]["mass_u"] = -1
    elif issue == "balance":
        m["reverse"]["kappa"] = 0.5
    elif issue == "standard":
        m["standard_states"] = dict(m["standard_states"], gas_pressure_Pa=1)
    elif issue == "graph":
        m["local_event"]["neighbors_zero_based"] = []
    elif issue == "entity":
        m["local_event"]["final"][1][1] = 2
    b = signed(n, m)
    if issue == "stale":
        b["models"][0]["accepted_by"] = "changed"
    with pytest.raises(ValueError, match=match):
        zacros(generate(n, b, verified_hashes={DIGEST}))


@pytest.mark.parametrize("value,unit", [(-1, "s^-1"), (math.inf, "s^-1"), (1, "mol kg^-1 s^-1"), (1, "Pa^-2 s^-1")])
def test_invalid_prefactor_or_normalization(value, unit):
    with pytest.raises(ValueError):
        normalized_prefactor(value, unit, 1, 1e5)


def test_missing_sticking_is_an_explicit_draft():
    n, m = case(gas=True)
    del m["forward"]["sticking"]
    d = dataset(n, m)
    assert d["reactions"][0]["rates"] == {"forward": None, "reverse": None}
    assert any("sticking" in gap for gap in d["reactions"][0]["missing"])
    assert not d["export_eligible"]


def test_pressure_standard_converts_before_detailed_balance():
    n, m = case(gas=True, standard_pa=2e5)
    d = dataset(n, m)
    row = catkinas(d)["rows"][0]
    assert row["forward"]["coefficient"] * 2 / row["reverse"]["coefficient"] == pytest.approx(ORACLE["K_400K_minus0.1eV"])
    assert row["P_bar"] == 1
    pair = row["fixed_T_energy_input"]
    for name, barrier in [("forward", pair["Ea_eV"]), ("reverse", pair["Ea_eV"] - pair["G0_eV"])]:
        predicted = 1.380649e-23 * 400 / 6.62607015e-34 * math.exp(-barrier * 1.602176634e-19 / (1.380649e-23 * 400))
        assert predicted == pytest.approx(row[name]["coefficient"])


def test_zacros_pattern_only_required_for_event_export():
    n, m = case()
    del m["local_event"]
    d = dataset(n, m)
    assert catkinas(d)["rows"] and d["reactions"][0]["local_event_missing"]
    with pytest.raises(ValueError, match="pattern"):
        zacros(d)


def test_shipped_benchmark_replays_both_exports():
    n, m = case(gas="dissociative")
    assert n == json.loads((FIX / "kinetic_interface_network.json").read_bytes())
    assert signed(n, m) == json.loads((FIX / "kinetic_interface_models.json").read_bytes())
    result = dataset(n, m)
    directory = ROOT / "reports/multiphase/phase2_4"
    for name, output in (("dataset", result), ("catkinas", catkinas(result)), ("zacros", zacros(result))):
        assert output == json.loads((directory / f"synthetic_interface_{name}.json").read_bytes())


def test_incompatible_temperature_rows_are_not_one_engine_model():
    n, m = case()
    data = dataset(n, m)
    hot, hm = case(temperature=600, barrier=0.35)
    data["reactions"].extend(dataset(hot, hm)["reactions"])
    del data["dataset_version"]
    data["dataset_version"] = sha256_json(data)
    with pytest.raises(ValueError, match="common temperature"):
        catkinas(data)


def test_synthetic_source_cannot_be_exported_as_project_evidence():
    n, m = case()
    m["use_scope"] = "project"
    with pytest.raises(ValueError, match="benchmark scope"):
        dataset(n, m)


def test_point_rate_uses_partial_pressure_and_each_vacant_site_once():
    n, m = case(gas="dissociative", standard_pa=2e5)
    row = dataset(n, m)["reactions"][0]
    args = dict(surface_activities={}, vacancy_activities={"top-Ni": 0.4, "bridge-Cu": 0.6})
    k = row["rates"]["forward"]["activity_coefficient_s^-1"]
    assert mean_field_rate(row, "forward", partial_pressures_pa={"H2-g": 50000}, **args) == pytest.approx(k * 0.25 * 0.4 * 0.6)
    assert mean_field_rate(row, "forward", partial_pressures_pa={"H2-g": 0}, **args) == 0
    with pytest.raises(ValueError, match="total pressure"):
        mean_field_rate(row, "forward", partial_pressures_pa={"H2-g": 110000}, **args)


def test_generate_new_tst_parameters_without_previous_rates():
    n, m = case(without_parameters=True)
    assert n["parameter_sets"] == [] and n["reactions"][0]["level"] == "SCIENTIFICALLY_ACCEPTED"
    d = dataset(n, m)
    row = d["reactions"][0]
    assert row["rates"]["forward"]["activity_coefficient_s^-1"] == pytest.approx(ORACLE["TST_s-1"]["400K_0.4eV"])
    assert row["rates"]["reverse"] and not d["export_eligible"]
    assert any("network-bound verified review" in gap for gap in row["missing"])


def test_real_fe_blocked_no_invented_values(tmp_path):
    d = generate(json.loads(FE.read_bytes()))
    r = d["reactions"][0]
    assert r["rates"] == {"forward": None, "reverse": None} and r["equilibrium"] is None
    assert all(v is None for v in r["energies"]["gibbs_ev"].values())
    assert r["energies"]["electronic_ev"] == pytest.approx(dict(forward=0.97360174, reverse=0.31429371, reaction=0.65930803))
    assert r["ts_local_zpe_ev"] == pytest.approx(0.51405165)
    assert any(s.startswith("IS:") for s in r["missing"]) and any(s.startswith("FS:") for s in r["missing"])
    assert not d["export_eligible"]
    for exporter in [catkinas, zacros]:
        with pytest.raises(ValueError, match="blocked"):
            exporter(d)
    target = tmp_path / "events.json"
    proc = subprocess.run([sys.executable, "-m", "scripts.kinetic_parameters", str(FE), "--format", "zacros",
                           "--output", str(target)], capture_output=True)
    assert proc.returncode and not target.exists()
