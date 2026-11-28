"""Exercise operator-approved external inputs without modifying package constants."""
from hashlib import sha256
import json
from pathlib import Path
import shutil

import pytest

from sbq123.common.evidence.registry import dataset
from sbq123.common.kinetic_model.contracts import Model


def test_external_model_and_companion(tmp_path, monkeypatch):
    from sbq123.reactor import simulate
    fixture = Path(__file__).resolve().parents[2] / "docs/v32/examples/project-trust"
    root = tmp_path / "project"
    shutil.copytree(fixture, root)
    record = json.loads((root / "kinetics.json").read_bytes())
    assert Model.from_record(record["model"]).provenance == "user_supplied"
    monkeypatch.delenv("SBQ123_PROJECT_TRUST_STORE", raising=False)
    monkeypatch.delenv("SBQ123_PROJECT_TRUST_SHA256", raising=False)
    with pytest.raises(ValueError):
        dataset("example-isomerization")
    monkeypatch.setenv("SBQ123_PROJECT_TRUST_STORE", str(root / "project.json"))
    monkeypatch.setenv("SBQ123_PROJECT_TRUST_SHA256", (fixture / "operator.sha256").read_text().strip())
    assert dataset("example-isomerization").digest == record["sha256"]
    args = dict(kind="CSTR", mode="fixed", dataset_id="example-isomerization", volume_m3=1, inlet_mol_s=1,
                reactant="A", product="B", temperature_K=400., pressure_Pa=400*8.31446261815324,
                composition={"A":1., "B":0.})
    result = simulate(**args)
    assert result["points"][0]["conversion"] == pytest.approx(.6/1.6)
    assert result["evidence_provenance"]["thermo_registry_sha256"] == sha256((root/"thermo.json").read_bytes()).hexdigest()
    (root / "thermo.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="independent review"):
        simulate(**args)
    assert dataset("example-isomerization").digest == record["sha256"]
    with (root / "project.json").open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="operator pin"):
        dataset("example-isomerization")


def _surface_project(tmp_path, monkeypatch, multisite=True, inert=False, multistable=False):
    """Manufactured inputs explicitly reviewed only for this software test."""
    from copy import deepcopy
    from sbq123.common.kinetic_model.contracts import identity
    src = Path(__file__).resolve().parents[2] / "src/sbq123"
    models = json.loads((src/"common/registries/datasets.json").read_bytes())["entries"]
    companion = json.loads((src/"reactor/registries/mechanisms.json").read_bytes())["records"]["langmuir"]
    model = models["three-surface-roots" if multistable else "langmuir"]["model"]
    if multisite:
        model["sites"].append("vacant2")
        model["species"].append(dict(model["species"][-1], name="A2*", sites={"vacant2":1}))
        for original in list(model["steps"]):
            step = deepcopy(original)
            for key in ("orders", "change"):
                step[key] = {{"A*":"A2*", "vacant":"vacant2"}.get(n,n):v for n,v in step[key].items()}
            step["coefficient"] *= 1.7 if "A" in step["orders"] else 1
            model["steps"].append(step)
        companion["thermo"].update({"vacant2":companion["thermo"]["vacant"], "A2*":companion["thermo"]["A*"]})
    if inert:
        model["species"].append(dict(name="I", phase="gas", elements={"He":1}, charge=0, sites={}))
        companion["element_weights_kg_kmol"]["He"] = 4.002602
        companion["thermo"]["I"] = companion["thermo"]["A"]
    pin = identity(model)
    companion.update(scope="reviewed_project", model_sha256=pin)
    companion["site_geometry"].update(catalyst="test-catalyst", conversion_id="test-density",
                                       site_densities_mol_m2=dict.fromkeys(model["sites"],1))
    records = []
    for kind, key, doc in [
            ("datasets","test-system",dict(model=model, sha256=pin, scope="reviewed_project")),
            ("thermo_companion","test-system",companion),
            ("catalysts","test-catalyst",dict(scope="reviewed_project",conversion_ids=["test-density"])),
            ("basis_conversions","test-density",dict(model_sha256=pin,mol_sites_per_kg=1.,approval="test only",scope="reviewed_project"))]:
        name = kind+".json"
        raw = json.dumps(doc).encode()
        (tmp_path/name).write_bytes(raw)
        records.append(dict(kind=kind,id=key,path=name,sha256=sha256(raw).hexdigest(),decision="approved",
                            reviewed_at="2026-11-28T00:00:00Z",reviewer="independent numerical test fixture"))
    raw = json.dumps(dict(format="sbq123-project-trust/1",project="manufactured control",records=records)).encode()
    (tmp_path/"project.json").write_bytes(raw)
    monkeypatch.setenv("SBQ123_PROJECT_TRUST_STORE", str(tmp_path/"project.json"))
    monkeypatch.setenv("SBQ123_PROJECT_TRUST_SHA256", sha256(raw).hexdigest())
    return dict(dataset_id="test-system", mode="fixed", volume_m3=1., inlet_mol_s=1., reactant="A", product="B",
                initial_coverage=[.05]*len(model["sites"]), catalyst="test-catalyst", conversion_id="test-density",
                catalyst_loading_kg=1., temperature_K=400., pressure_Pa=400*8.31446261815324,
                composition=({"A":.8,"B":0.,"I":.2} if inert else {"A":1.,"B":0.}))


@pytest.mark.parametrize("mode", ["fixed", "dynamic_mkm"])
def test_independent_sites_and_inert_pfr(tmp_path, monkeypatch, mode):
    from sbq123.reactor import simulate
    args = _surface_project(tmp_path, monkeypatch, inert=True)
    args["mode"] = mode
    out = simulate("PFR", area_m2=1., **args)
    end = out["points"][-1]
    assert end["conversion"] > 0 and end["amount_or_flow"]["I"] == pytest.approx(.2)
    assert end["coverage"][0] != pytest.approx(end["coverage"][1])
    assert all(v+c == pytest.approx(1.) for v,c in zip(end["vacancy"],end["coverage"],strict=True))
    assert abs(end["mass_residual_kg_s"]) < 1e-9


def test_slow_surface_at_high_ghsv_with_joint_seed(tmp_path, monkeypatch):
    from sbq123.reactor import simulate
    args = _surface_project(tmp_path, monkeypatch, multisite=False)
    args.update(volume_m3=1e-7,catalyst_loading_kg=1e-7,cstr_seeds=[{"gas_flow_mol_s":[1.,0.],"surface_coverage":[.9]}])
    out = simulate("CSTR", **args)
    end = out["points"][0]
    assert end["coverage"][0] == pytest.approx(.5,abs=2e-6)
    assert end["conversion"] > 0
    assert any(s.get("seed_surface_coverage")==[.9] and s["status"]=="converged" for s in out["solver"]["seed_outcomes"])


def test_non_equimolar_fixed_momentum(monkeypatch):
    from copy import deepcopy
    import importlib
    from sbq123.common.kinetic_model.contracts import identity
    from sbq123.reactor import simulate
    owner=importlib.import_module("sbq123.reactor.mechanism")
    c,raw=deepcopy(owner._record("first-order"))
    raw["species"][1]["elements"]["X"]=2
    raw["steps"][0].update(orders={"A":2},change={"A":-2,"B":1})
    c["model_sha256"]=identity(raw)
    monkeypatch.setattr(owner,"_record",lambda key:(c,raw))
    p=400*8.31446261815324
    out=simulate("PFR",mode="fixed",dataset_id="2A-to-B-test",reactant="A",product="B",volume_m3=1.,
                 area_m2=.1,inlet_mol_s=1.,composition={"A":1.,"B":0.},temperature_K=400.,pressure_Pa=p)
    row=out["points"][-1]
    assert abs(row["pressure_Pa"]/p-1)>2e-7
    assert row["amount_or_flow"]["A"]+2*row["amount_or_flow"]["B"] == pytest.approx(1.)
    assert row["selectivity_mol_per_mol_consumed"] == pytest.approx(.5)


def test_joint_seed_distinguishes_surface_roots(tmp_path, monkeypatch):
    from sbq123.reactor import simulate
    args = _surface_project(tmp_path, monkeypatch, multisite=False, multistable=True)
    args.update(mode="dynamic_mkm", initial_coverage=[.2], cstr_seeds=[
        {"gas_flow_mol_s":[1.,0.],"surface_coverage":[.8]}])
    result = simulate("CSTR", **args)
    roots = [p["coverage"][0] for p in result["points"]]
    assert min(abs(v-.2) for v in roots) < 1e-6
    assert min(abs(v-.8) for v in roots) < 1e-6
    assert len(set(p["root_sha256"] for p in result["points"])) == len(roots)


def test_rate_replay_precision_preserves_inputs():
    import math
    from copy import deepcopy
    from sbq123.common.kinetic_model.contracts import identity
    from sbq123.common.kinetic_model.replay_precision import same_recalculation
    def seal(doc):
        doc["dataset_version"] = identity({k:v for k,v in doc.items() if k != "dataset_version"})
        return doc
    field = "activity_coefficient_s^-1"
    original = seal({"source":"independent", "reactions":[{"reaction_id":"a","rates":{"forward":{field:1.0}}}]})
    rebuilt = deepcopy(original)
    for i in range(5):
        rate = rebuilt["reactions"][0]["rates"]["forward"]
        rate[field] = math.nextafter(rate[field], math.inf)
        assert same_recalculation(original, seal(rebuilt)) is (i < 4)
    rebuilt = deepcopy(original)
    rebuilt["source"] = "different"
    assert not same_recalculation(original, seal(rebuilt))


def test_external_reactor_result_identity(approve_project_record):
    from sbq123.analysis.__main__ import file_qualification
    pin = sha256(b"external producer receipt").hexdigest()
    assert file_qualification(pin).startswith("reported_only")
    approve_project_record("reactor_result",pin)
    assert file_qualification(pin) == "independently_reviewed_results"
    assert file_qualification("0"*64).startswith("reported_only")
