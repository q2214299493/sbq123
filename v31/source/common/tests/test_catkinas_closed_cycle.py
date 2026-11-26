"""Synthetic full-entry-point CATKINAS test. The fixture reviews apply only to software verification."""
import json
import math
import subprocess
import sys
from copy import deepcopy

import pytest
import numpy as np
from scipy.io import loadmat, savemat
from scipy.optimize import root

from scripts.artifact_io import sha256_file
from scripts.baseline_mkm.results import read_single_point
from scripts.kinetic_parameters.engine import generate
from scripts.native_model import assemble
from scripts.reaction_network.builder import build_network
from scripts.thermochemistry.harmonic import H_J_S, KB_J_K
from test_kinetic_parameters import DIGEST, FIX, ROOT, case, signed

OUT = ROOT / "reports/multiphase/phase2_5_2"
REFERENCE = FIX / "closed_cycle_reference.json"


def cycle_model(system="interface", *, with_network=False, temperature_K=400, pressure_Pa=160000):
    ref = json.loads(REFERENCE.read_bytes())
    n, adsorption = case(system=system, gas="dissociative")
    species = n["species"]
    templates = {s["species_id"]: s for s in species}
    for sid, template, composition in (("NO-g", "H2-g", {"N": 1, "O": 1}), ("HNO-g", "H2-g", {"H": 1, "N": 1, "O": 1}),
                                       ("HNO-top", "H2-top", {"H": 1, "N": 1, "O": 1})):
        species.append(dict(deepcopy(templates[template]), species_id=sid, structure_id=sid, composition=composition))
    source = {"kind": "synthetic", "reference": REFERENCE.name, "sha256": sha256_file(REFERENCE)}
    hashes = {DIGEST, source["sha256"]}
    model_rows, reviews = [], []
    bundle = dict(n["catalog"], schema_version="1.0.0", species=species, reactions=[], parameter_sets=[], runs=[])
    specs = [
        ("ads", {"H2-g": 1}, {"H2-top": 1, "H2-bridge": 1}, {"top-Ni": 1, "bridge-Cu": 1}, {}),
        ("transfer", {"H2-bridge": 1}, {"H2-top": 1}, {"top-Ni": 1}, {"bridge-Cu": 1}),
        ("hydrogenate", {"H2-top": 1, "NO-g": 1}, {"HNO-top": 1}, {}, {}),
        ("desorb", {"HNO-top": 1}, {"HNO-g": 1}, {}, {"top-Ni": 1}),
    ]
    g = ref["formation_G_eV"]
    for rid, left, right, consumed, released in specs:
        reaction = deepcopy(n["reactions"][0]["definition"])
        p = deepcopy(n["parameter_sets"][0])
        required = {"top-Ni": 1, "bridge-Cu": 1} if rid in ("ads", "transfer") else {"top-Ni": 1}
        reaction.update(reaction_id=rid, reactants=left, products=right, required_sites=required, sites_consumed=consumed,
                        sites_released=released, ts_id="fixture-ts-"+rid, initial_structure_id="fixture-is-"+rid,
                        final_structure_id="fixture-fs-"+rid)
        p.update(reaction_id=rid, parameter_set_id="parameters-"+rid, pressure_Pa=pressure_Pa)
        # This software fixture has explicitly temperature-independent model free energies.
        reaction["free_energies"]["temperature_K"] = p["temperature_K"] = temperature_K
        p["validity_range"]["max_pressure_Pa"] = 160000
        gl = sum(g[s]*v for s, v in left.items())
        gr = sum(g[s]*v for s, v in right.items())
        ts = ref["transition_state_G_eV"][rid]
        m = deepcopy(adsorption)
        m.update(reaction_id=rid, parameter_set_id=p["parameter_set_id"], sources=[*m["sources"], source])
        for key, value in {"forward": ts-gl, "reverse": ts-gr, "reaction": gr-gl}.items():
            reaction["free_energies"]["values"][key]["value"] = value
        if rid != "ads":
            reaction["reaction_type"] = {"transfer": "diffusion", "hydrogenate": "association", "desorb": "desorption"}[rid]
            fixture = {"path": REFERENCE.relative_to(ROOT).as_posix(), "sha256": source["sha256"]}
            for record in [*reaction["provenance"], *p["sources"], *(v["source"] for v in reaction["electronic_energies"].values()),
                           *(v["source"] for v in reaction["free_energies"]["values"].values()),
                           *(p[direction]["activation_energy"]["source"] for direction in ("forward", "reverse"))]:
                record.update(calculation_id="synthetic-cycle-"+rid, artifact=fixture)
            # All values belong to this toy Hamiltonian: the declared synthetic thermal increment is zero.
            for key, record in reaction["electronic_energies"].items():
                record["value"] = reaction["free_energies"]["values"][key]["value"]
            del m["local_event"]
            for direction, terms in (("forward", left), ("reverse", right)):
                m[direction] = {"method": "prefactor"}
                gas = any(s.endswith("-g") for s in terms)
                p[direction].update(prefactor=KB_J_K*400/H_J_S/(100000 if gas else 1),
                                    prefactor_unit="Pa^-1 s^-1" if gas else "s^-1")
        for direction in ("forward", "reverse"):
            p[direction]["activation_energy"]["value"] = reaction["free_energies"]["values"][direction]["value"]
        bundle["reactions"].append(reaction)
        bundle["parameter_sets"].append(p)
        model_rows.append(m)
        reviews.append(dict(reaction_id=rid, grade="A", structure_identity=reaction["ts_id"],
                            assignment="synthetic fixture", review_reference=REFERENCE.name))
    options = dict(verified_hashes=hashes, ts_reviews=reviews, sources=n["source_artifacts"] + [
        {"role": "verified_evidence", "sha256": source["sha256"], "file": REFERENCE.name}])
    network = build_network(bundle, **options)
    decisions = [dict(subject_sha256=r["subject_sha256"], reaction_id=r["definition"]["reaction_id"], decision="accepted",
                      reviewer="synthetic fixture", reason="software benchmark only", reviewed_at="2026-11-19T00:00:00Z")
                 for r in network["reactions"]]
    network = build_network(bundle, decisions=decisions, **options)
    bindings = {"network_version": network["network_version"], "models": [signed(network, m)["models"][0] for m in model_rows]}
    d = generate(network, bindings, verified_hashes=hashes)
    c = {"dataset_version": d["dataset_version"], "partial_pressure_bar": ref["partial_pressure_bar"],
         "catkinas": {"aliases": {"H2-g": "H2", "NO-g": "NO", "HNO-g": "HNO", "H2-top": "H", "H2-bridge": "H", "HNO-top": "HNO"},
                      "initial_coverages": {"H2-top": 0, "H2-bridge": 0, "HNO-top": 0}, "MaxTime": 3, "MaxOdeTime": 3}}
    return (network, d, c) if with_network else (d, c)


def test_closed_cycle_replays_unchanged_adsorption_equation():
    d, c = cycle_model()
    files, m = assemble("catkinas", d, c)
    content = files["INPUT_phase25.m"]
    assert content.encode() == (OUT/"catkinas_closed_cycle_input.m").read_bytes()
    assert (ROOT/"reports/multiphase/phase2_5/catkinas/INPUT_phase25.m").read_text().splitlines()[0] in content
    assert m["validation"]["native_text_readback"]["equation_count"] == 4
    assert all(r["model"]["use_scope"] == "synthetic_benchmark" for r in d["reactions"])
    assert d == json.loads((OUT/"cycle_dataset.json").read_bytes())
    assert c == json.loads((OUT/"cycle_configuration.json").read_bytes())


def independent_constants():
    """SI constants and literal activities; independent of the CATKINAS export and parser."""
    kbt = 1.380649e-23 * 400
    kt = kbt / 1.602176634e-19
    collision = 0.25 * 5e-20 * 1e5 / math.sqrt(2*math.pi*2*1.66053906892e-27*kbt)
    fw = np.array([collision*math.exp(-0.4/kt), *[kbt/6.62607015e-34*math.exp(-b/kt) for b in (0.76, 0.78, 0.8)]])
    return fw, fw*np.exp(np.array([-0.1, 0.02, -0.1, 0.06])/kt)


def independent_flux(theta, kf, kr):
    h1, hno, h2 = theta
    v1, v2 = 1-h1-hno, 1-h2
    return kf*np.array([1.0*v1*v2, h2*v1, 0.5*h1, hno]), kr*np.array([h1*h2, h1*v2, hno, 0.1*v1])


def residual(r):
    return np.array([r[0]+r[1]-r[2], r[2]-r[3], r[0]-r[1]])


def test_independent_steady_state_and_phase24_adsorption_constants():
    record = read_single_point(OUT/"data1.mat", OUT/"native_log_extract.txt")
    rf, rr = independent_constants()
    def rhs(theta):
        f, r = independent_flux(theta, rf, rr)
        return residual(f-r)
    solution = root(rhs, [0.25, 0.25, 0.5], tol=1e-11)
    assert solution.success and np.max(abs(rhs(solution.x))) < 1e-8
    y = record["coverages"]
    observed = [y["Q1_H"], y["Q1_HNO"], y["Q2_H"]]
    np.testing.assert_allclose(solution.x, observed, rtol=1e-4)
    assert rf[0] == pytest.approx(1062.5043325104702, rel=1e-12)
    assert rr[0] == pytest.approx(58.396411910597834, rel=1e-12)
    native = record["reactions"]
    for k, arr in (("kf", rf), ("kr", rr), ("forward_flux", independent_flux(solution.x, rf, rr)[0]),
                   ("reverse_flux", independent_flux(solution.x, rf, rr)[1]), ("net_flux", np.subtract(*independent_flux(solution.x, rf, rr)))):
        np.testing.assert_allclose([r[k] for r in native], arr, rtol=1e-4)
    assert record["partial_pressures_bar"] == {"P_H2": 1.0, "P_NO": 0.5, "P_HNO": 0.1}
    assert abs(sum(y[k] for k in ("Q1_H", "Q1_HNO", "Q1_v"))-1) < 1e-8
    assert abs(y["Q2_H"]+y["Q2_v"]-1) < 1e-8
    net = np.array([r["net_flux"] for r in native])
    assert max(abs(residual(net)))/max(abs(net)) < 1e-7
    gas = record["net_gas_flux_per_reference_site_s"]
    assert abs(2*gas["H2"] + gas["HNO"]) < 1e-8 and abs(gas["NO"]+gas["HNO"]) < 1e-8
    assert np.all(net > 0)


def test_closed_cycle_balance_and_native_mass_action():
    d, _ = cycle_model()
    site = {s["species_id"]: s["site_occupancy"] for s in d["species"]}
    atoms = {s["species_id"]: s["composition"] for s in d["species"]}
    for row in d["reactions"]:
        f = row["direction"]["forward"]
        for atom in ("N", "O", "H"):
            assert sum(n*atoms[s].get(atom, 0) for s, n in f["reactants"].items()) == sum(
                n*atoms[s].get(atom, 0) for s, n in f["products"].items())
        for label in ("top-Ni", "bridge-Cu"):
            left = f["sites_consumed"].get(label, 0) + sum(n*site[s].get(label, 0) for s, n in f["reactants"].items())
            right = f["sites_released"].get(label, 0) + sum(n*site[s].get(label, 0) for s, n in f["products"].items())
            assert left == right
    out = read_single_point(OUT/"data1.mat", OUT/"native_log_extract.txt")
    kf = np.array([r["kf"] for r in out["reactions"]])
    kr = np.array([r["kr"] for r in out["reactions"]])
    theta = [out["coverages"][s] for s in ("Q1_H", "Q1_HNO", "Q2_H")]
    for column, predicted in zip(("forward_flux", "reverse_flux"), independent_flux(theta, kf, kr), strict=True):
        np.testing.assert_allclose([r[column] for r in out["reactions"]], predicted, rtol=1e-12)
    log = (OUT/"native_log_extract.txt").read_text()
    assert "z1 = (Q1_H*Q2_H)/(P_H2*Q1_v*Q2_v*Keq(1))" in log
    assert "H2(gas) + 2 NO(gas) <-> 2 HNO(gas)" in log
    energy = np.array([r["applied_reaction_energy_eV"] for r in out["reactions"]])
    native_barriers = np.array([r["applied_forward_barrier_eV"] for r in out["reactions"]])
    np.testing.assert_allclose(energy, [-0.1, 0.02, -0.1, 0.06], atol=1e-14)
    np.testing.assert_allclose(native_barriers, [0.7853168271366968, 0.76, 0.78, 0.80], atol=1e-14, rtol=0)
    np.testing.assert_allclose(native_barriers-energy, [0.8853168271366968, 0.74, 0.88, 0.74], atol=1e-14, rtol=0)
    np.testing.assert_allclose(kf/kr, np.exp(-energy/(8.617333262145e-5*400)), rtol=1e-4)
    assert np.dot(energy, [1, 1, 2, 2]) == pytest.approx(-0.16)


def test_single_point_reader_cli_and_archived_observation():
    result = subprocess.run([sys.executable, "-m", "scripts.baseline_mkm.results", OUT/"data1.mat", OUT/"native_log_extract.txt"],
                            cwd=ROOT, check=True, capture_output=True)
    receipt = json.loads((OUT/"catkinas_closed_cycle_validation.json").read_bytes())
    assert json.loads(result.stdout) == receipt["native_single_point"]
    assert sha256_file(OUT/"data1.mat") == receipt["closed_cycle"]["result_sha256"]["result_closed_cycle/data1.mat"]


@pytest.mark.parametrize("defect", ["missing_kr", "shape", "infinite", "net", "negative", "mapping", "gas_table", "unconverged", "unfinished"])
def test_result_reader_rejects_malformed_native_output(defect, tmp_path):
    data = {k: v for k, v in loadmat(OUT/"data1.mat").items() if not k.startswith("_")}
    log = (OUT/"native_log_extract.txt").read_text()
    if defect == "missing_kr":
        del data["kr"]
    elif defect == "shape":
        data["R"] = data["R"][0]
    elif defect == "infinite":
        data["R"][0, 0, 0] = math.inf
    elif defect == "net":
        data["Rnet"][0, 0] += 1
    elif defect == "negative":
        data["kf"][0, 0] = -1
    elif defect == "mapping":
        log = log.replace("y(2)", "y(1)")
    elif defect == "gas_table":
        log = log.replace("HNO(gas)", "N2(gas)")
    elif defect == "unconverged":
        log = log.replace("Succeed!!", "Failed")
    else:
        log = log.replace("CATKINAS is finished now", "interrupted")
    path = tmp_path/"data.mat"
    savemat(path, data)
    (tmp_path/"log1").write_text(log)
    with pytest.raises(ValueError):
        read_single_point(path, tmp_path/"log1")
