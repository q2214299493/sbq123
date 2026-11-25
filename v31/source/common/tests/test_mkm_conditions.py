"""Offline CATKINAS grid tests. The live process is always replaced by MAT replay."""
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator
import numpy as np
import pytest
from scipy.io import loadmat, savemat
from scipy.optimize import root

import test_catkinas_closed_cycle as cycle
from scripts.kinetic_parameters.export import catkinas
from test_catkinas_closed_cycle import cycle_model, residual

from scripts.artifact_io import sha256_file, write_json_exclusive as save
from scripts.baseline_mkm import condition_scan as scan
from scripts.baseline_mkm import single_point as point
from test_mkm_single_point import OUT, PHASE, make_decision, replay, runtime  # noqa: F401

PROFILE = PHASE.parent / "phase3_1/benchmark_normalization.json"
ROOT = PHASE.parents[2]


def ref(path):
    return {"path": str(path), "sha256": sha256_file(path)}


def request():
    return dict(format="catkinas-condition-grid/1", temperatures_K=[400, 450], pressure_species_id="H2-g",
                feeds_bar=[{"H2-g": 1, "NO-g": 0.5, "HNO-g": 0.1}, {"H2-g": 0.9, "NO-g": 0.6, "HNO-g": 0.1}],
                models=[dict(temperature_K=400, total_pressure_bar=1.6, network=ref(PHASE / "closed_cycle_network.json"),
                             dataset=ref(OUT / "cycle_dataset.json"), configuration=ref(PHASE / "workflow_configuration.json"),
                             normalization=ref(PROFILE))])


def prepare(tmp_path, runtime, spec):  # noqa: F811
    manifest = scan.prepare(tmp_path / "grid", save(tmp_path / "request.json", spec), *runtime, tmp_path / "stub")
    return Path(manifest["manifest"]), manifest["sha256"]


@pytest.mark.parametrize(("temperatures", "feeds", "count"), [([400, 450], 1, 2), ([400], 2, 2), ([400, 450], 2, 4)])
def test_requested_coordinates_preserved(tmp_path, runtime, temperatures, feeds, count):  # noqa: F811
    spec = request()
    spec.update(temperatures_K=temperatures, feeds_bar=spec["feeds_bar"][:feeds])
    path, digest = prepare(tmp_path, runtime, spec)
    report = scan.collect(path, digest)
    assert len(report["points"]) == count
    for row in report["points"]:
        assert row["status"] == ("AWAITING_APPROVAL" if row["temperature_K"] == 400 else "UNQUALIFIED")
        assert row["result"] is None and row["convergence"] == "unknown"
    assert len(report["comparisons"]) == (len(temperatures)-1)*feeds + (feeds-1)*len(temperatures)
    assert all(x["delta"] is None for x in report["comparisons"])


@pytest.mark.parametrize("defect", ["duplicate_temperature", "duplicate_pressure", "missing_gas", "unknown_axis",
                                    "tampered", "wrong_temperature", "wrong_total"])
def test_bad_grid_or_binding(tmp_path, runtime, defect):  # noqa: F811
    s = request()
    if defect == "duplicate_temperature":
        s["temperatures_K"] = [400, 400]
    elif defect == "duplicate_pressure":
        s["feeds_bar"][1]["H2-g"] = 1
    elif defect == "missing_gas":
        del s["feeds_bar"][1]["NO-g"]
    elif defect == "unknown_axis":
        s["pressure_species_id"] = "unknown"
    elif defect == "tampered":
        s["models"][0]["network"]["sha256"] = "0"*64
    elif defect == "wrong_temperature":
        s["models"][0]["temperature_K"] = 450
    else:
        s["models"][0]["total_pressure_bar"] = 1.5
    if defect in ("duplicate_temperature", "duplicate_pressure", "missing_gas", "unknown_axis"):
        with pytest.raises(ValueError):
            prepare(tmp_path, runtime, s)
    else:
        path, digest = prepare(tmp_path, runtime, s)
        assert all(p["status"] == "UNQUALIFIED" for p in scan.collect(path, digest)["points"])


@pytest.mark.parametrize("physical", [True, False])
def test_replay_and_rejection(tmp_path, runtime, monkeypatch, physical):  # noqa: F811
    s = request()
    if not physical:
        config = point.read(PHASE / "workflow_configuration.json")
        del config["turnover_basis"]
        s["models"][0].update(configuration=ref(save(tmp_path / "native.json", config)), normalization=None)
    builder = point.tools_for_run
    monkeypatch.setattr(point, "tools_for_run", lambda p: dict(builder(p), matlab_sha256="0"*64))
    path, digest = prepare(tmp_path, runtime, s)
    monkeypatch.setattr(point, "launch", lambda d, e: replay(d))
    for row in point.read(path)["points"][:2]:
        run = path.parent / row["run"]
        decision = save(run / "fixture-decision.json", make_decision(run, PHASE / "benchmark_ticket_fixture.json"))
        point.execute(run, decision)
    report = scan.collect(path, digest)
    a, failed, *blocked = report["points"]
    assert a["status"] == "QUALIFIED", a
    assert a["convergence"] == "converged"
    r = a["result"]
    assert len(r["coverage"]) == 3 and len(r["reactions"]) == 4 and r["molar_selectivity"] == {"HNO-g": 1}
    assert r["tof"]["per_reference_s"] == (81.5127701616477 if physical else None)
    assert (r["normalization"] is not None) == physical
    assert r["tof_qualification"] == ("qualified" if physical else "unavailable")
    assert all(k["gibbs_temperature_K"] == 400 and abs(k["equilibrium"]["log_ratio_residual"]) <= 1e-6
               for k in r["kinetic_applicability"].values())
    assert failed["status"] == "REJECTED" and failed["result"] is None and failed["reason"]
    assert all(row["status"] == "UNQUALIFIED" for row in blocked)
    Draft202012Validator(point.read(ROOT / "configs/kinetics/catkinas_condition_result.schema.json")).validate(report)
    with pytest.raises(ValueError, match="SHA"):
        scan.collect(path, "f"*64)
    run = path.parent / a["run"]
    with (run / "runtime/result_phase25/data1.mat").open("ab") as stream:
        stream.write(b"tampered")
    assert scan.collect(path, digest)["points"][0]["status"] == "INVALID_EVIDENCE"


def test_delta_respects_physical_reference():
    a = dict(coverage={"X": .1}, net_rate={"r": 4.0}, tof={"per_reference_s": 8.0}, molar_selectivity={"X": 1.0},
             runtime=["same"], normalization={"network_version": "v1", "evidence_sha256": "one"}, net_rate_unit="pair/s")
    b = deepcopy(a)
    b.update(coverage={"X": .3}, net_rate={"r": 6.0}, tof={"per_reference_s": 12.0})
    b["normalization"]["network_version"] = "v2"
    delta = scan.deltas(a, b)
    assert delta["coverage"]["X"] == pytest.approx(.2) and delta["net_rate"]["r"] == 2 and delta["tof"] == 4
    b["normalization"]["evidence_sha256"] = "different"
    delta = scan.deltas(a, b)
    assert delta["coverage"]["X"] == pytest.approx(.2) and delta["net_rate"] is delta["tof"] is None


def synthetic_map_point(directory, executable):
    """Make deterministic MAT-shaped observations only inside a temporary software fixture."""
    replay(directory)
    run = directory.parent
    cfg, data = (point.read(run / (k + ".json")) for k in ("configuration", "dataset"))
    rows = catkinas(data)["rows"]
    t = rows[0]["T_K"]
    feed = cfg["partial_pressure_bar"]
    h, no, hno = (feed[k] for k in ("H2-g", "NO-g", "HNO-g"))
    kf, kr = (np.array([r[side]["coefficient"] for r in rows]) for side in ("forward", "reverse"))

    def flux(theta):
        x, z, y = theta
        vac1, vac2 = 1-x-z, 1-y
        return kf * [h*vac1*vac2, y*vac1, no*x, z], kr * [x*y, x*vac2, z, hno*vac1]

    solution = root(lambda theta: residual(np.subtract(*flux(theta))), [.31, .4, .69], tol=1e-12)
    assert solution.success
    f, r = flux(solution.x)
    net = f-r
    x, z, y = solution.x
    folder = directory / "result_phase25"
    mat = folder / "data1.mat"
    values = {k: v for k, v in loadmat(mat).items() if not k.startswith("_")}
    for k, name in (("Ean", "Ea_eV"), ("Eao", "Ea_eV"), ("G0n", "G0_eV"), ("G0o", "G0_eV")):
        values[k] = [[row["fixed_T_energy_input"][name] for row in rows]]
    values.update(kf=[kf], kr=[kr], y=[[x, z, 1-x-z, y, 1-y]], params=[[h, hno, no]],
                  R=[np.column_stack((f, r, net))], Rnet=[net], Rnets=[[-net[0], net[3], -net[2]]])
    savemat(mat, values)
    log = folder / "log1"
    log.write_text(log.read_text().replace("T = 400;", f"T = {t};"))
    return 0


def second_model(tmp_path, t, pressure, feed):
    n, d, c = cycle_model(with_network=True, temperature_K=t, pressure_Pa=pressure)
    c["partial_pressure_bar"] = feed
    c.update({k: point.read(PHASE / "workflow_configuration.json")[k]
              for k in ("overall_stoichiometry", "selectivity_products", "turnover_basis")})
    profile = point.read(PROFILE)
    profile["network_version"] = n["network_version"]
    profile["source"]["path"] = str((PROFILE.parent / profile["source"]["path"]).resolve())
    second = dict(temperature_K=t, total_pressure_bar=pressure/1e5)
    for key, doc in (("network", n), ("dataset", d), ("configuration", c), ("normalization", profile)):
        second[key] = ref(save(tmp_path / (key + ".json"), doc))
    return second


@pytest.mark.parametrize("pressure_only", [False, True])
def test_complete_temperature_pressure_map(tmp_path, runtime, monkeypatch, pressure_only):  # noqa: F811
    s = request()
    if pressure_only:
        s["temperatures_K"] = [400]
        s["feeds_bar"][1]["NO-g"] = .5
    s["models"].append(second_model(tmp_path, 400 if pressure_only else 450, 150000 if pressure_only else 160000,
                                    s["feeds_bar"][1]))
    builder = point.tools_for_run
    monkeypatch.setattr(point, "tools_for_run", lambda p: dict(builder(p), matlab_sha256="0"*64))
    path, digest = prepare(tmp_path, runtime, s)
    monkeypatch.setattr(point, "launch", synthetic_map_point)
    for row in point.read(path)["points"]:
        assert row["reason"] is None, row
        run = path.parent / row["run"]
        decision = save(run / "mock-approval.json", make_decision(run, PHASE / "benchmark_ticket_fixture.json"))
        assert point.execute(run, decision)["stage"] == "ACCEPTED"
    result = scan.collect(path, digest)
    assert [(p["temperature_K"], p["partial_pressure_bar"]["H2-g"]) for p in result["points"]] == [
        (t, f["H2-g"]) for t in s["temperatures_K"] for f in s["feeds_bar"]]
    assert all(p["status"] == "QUALIFIED" for p in result["points"])
    by_id = {p["run"]: p["result"] for p in result["points"]}
    assert len({p["plan_sha256"] for p in by_id.values()}) == len(result["points"])
    for edge in result["comparisons"]:
        a, b = (by_id[edge[k]] for k in ("start", "end"))
        delta = edge["delta"]["tof"]
        assert delta == pytest.approx(b["tof"]["per_reference_s"]-a["tof"]["per_reference_s"]) and delta != 0


def test_changed_solver_is_not_a_temperature_effect(tmp_path, runtime):  # noqa: F811
    spec = request()
    second = second_model(tmp_path, 450, 160000, spec["feeds_bar"][0])
    cfg = point.read(Path(second["configuration"]["path"]))
    cfg["catkinas"]["MaxOdeTime"] += 1
    second["configuration"] = ref(save(tmp_path / "changed-solver.json", cfg))
    spec["models"].append(second)
    path, digest = prepare(tmp_path, runtime, spec)
    rows = scan.collect(path, digest)["points"]
    assert all(r["status"] == "AWAITING_APPROVAL" for r in rows[:2])
    assert all("Model family differs" in r["reason"] for r in rows[2:])


def test_native_only_delta_requires_same_native_model():
    a = dict(coverage={"X": .1}, net_rate={"r": 4}, tof={"per_reference_s": None}, molar_selectivity=None,
             runtime=["same"], normalization=None, net_rate_unit="model-native", dataset_sha256="d", network_sha256="n")
    b = dict(a, net_rate={"r": 6})
    assert scan.deltas(a, b) == dict(coverage={"X": 0}, net_rate={"r": 2}, tof=None, molar_selectivity=None)
    b["dataset_sha256"] = "another"
    assert scan.deltas(a, b)["net_rate"] is None


def test_missing_profile_is_local_to_its_condition(tmp_path, runtime):  # noqa: F811
    s = request()
    s["models"].append(second_model(tmp_path, 450, 160000, s["feeds_bar"][0]))
    s["models"][0]["normalization"]["path"] = str(tmp_path / "missing-profile.json")
    path, digest = prepare(tmp_path, runtime, s)
    points = scan.collect(path, digest)["points"]
    assert [p["status"] for p in points] == ["UNQUALIFIED"] * 2 + ["AWAITING_APPROVAL"] * 2


@pytest.mark.parametrize("change,expected", [
    ("gibbs", "AWAITING_APPROVAL"), ("prefactor", "AWAITING_APPROVAL"), ("pressure", "AWAITING_APPROVAL"),
    ("structure", "UNQUALIFIED"), ("site", "UNQUALIFIED"), ("intake", "UNQUALIFIED"),
])
def test_condition_evidence_partition(tmp_path, runtime, monkeypatch, change, expected):  # noqa: F811
    spec = request()
    spec["feeds_bar"] = spec["feeds_bar"][:1]
    temperature, pressure = 450, 160000
    if change == "pressure":
        temperature, pressure = 400, 150000
        spec["temperatures_K"] = [400]
        spec["feeds_bar"].append({"H2-g": 0.9, "NO-g": 0.5, "HNO-g": 0.1})
    artifact = ref(save(tmp_path / "evidence.json", {"fixture": change, "temperature": temperature, "pressure": pressure}))
    build = cycle.build_network

    def altered(bundle, **options):
        bundle = deepcopy(bundle)
        evidence = dict(file="evidence.json", sha256=artifact["sha256"], role="verified_evidence")
        if change in ("gibbs", "prefactor", "pressure"):
            options["sources"] = [*options["sources"], evidence]
            options["verified_hashes"] = options["verified_hashes"] | {artifact["sha256"]}
        if change == "gibbs":
            # The 400 K files serve both structural and thermal roles. At 450 K only
            # their electronic/structural role remains, with fresh reviewed thermal evidence.
            for rxn, param in zip(bundle["reactions"], bundle["parameter_sets"], strict=True):
                param["validation"]["review"] = artifact
                for record in [*rxn["provenance"], *param["sources"]]:
                    if record["kind"] == "thermal_correction":
                        record["artifact"] = artifact
                for side, term in rxn["free_energies"]["values"].items():
                    term["source"]["artifact"] = artifact
                    if side != "reaction":
                        term["value"] += 0.01
                        param[side]["activation_energy"] = deepcopy(term)
        elif change in ("prefactor", "pressure"):
            params = bundle["parameter_sets"][1]
            params["validation"]["review"] = artifact
            for side in ("forward", "reverse"):
                params[side]["prefactor"] *= 2
        elif change == "structure":
            bundle["surfaces"][0]["structural_provenance"] = ref(cycle.REFERENCE)
        elif change == "site":
            bundle["sites"][0]["local_geometry"] = "two adjacent atoms"
        else:
            options["sources"] = [*options["sources"], dict(evidence, role="intake")]
        return build(bundle, **options)

    monkeypatch.setattr(cycle, "build_network", altered)
    spec["models"].append(second_model(tmp_path, temperature, pressure, spec["feeds_bar"][-1]))
    second = spec["models"][1]
    # Both points must pass the independent single-point gate before testing family membership.
    point.qualify(*(point.read(Path(second[k]["path"])) for k in ("network", "dataset", "configuration")))
    path, digest = prepare(tmp_path, runtime, spec)
    first, second = scan.collect(path, digest)["points"]
    assert first["status"] == "AWAITING_APPROVAL"
    assert second["status"] == expected, second["reason"]
    if expected == "UNQUALIFIED":
        assert "Model family differs" in second["reason"] and second["plan_sha256"] is None


def project_model(directory, monkeypatch, spec, temperature, method, conventions, *, missing=None):
    """Use the normal network builder and review signatures on temporary software-only sources."""
    directory.mkdir()
    evidence = [ref(save(directory / (name + ".json"), {"fixture": value})) for name, value in
                (("method", method), ("conventions", conventions))]
    parent = point.read(PHASE / "closed_cycle_network.json")
    identity = dict(format="catkinas-electronic-identity/1",
                    electronic_sources=sorted(s["sha256"] for s in parent["source_artifacts"]),
                    dft_method_sha256=evidence[0]["sha256"], electronic_conventions_sha256=evidence[1]["sha256"])
    if missing == "electronic_source":
        identity["electronic_sources"].pop()
    if missing == "method":
        identity["dft_method_sha256"] = "0"*64
    if temperature != 400:
        identity["electronic_sources"].reverse()  # Source order carries no physical meaning.
    identity_ref = ref(save(directory / "identity.json", identity))
    build, sign = cycle.build_network, cycle.signed

    def bound_network(bundle, **options):
        refs = [*evidence, identity_ref]
        options["verified_hashes"] = options["verified_hashes"] | {r["sha256"] for r in refs}
        options["sources"] = [*options["sources"], *(dict(role="verified_evidence", file=Path(r["path"]).name,
                              sha256=r["sha256"]) for r in refs)]
        return build(bundle, **options)

    def bound_model(network, model):
        model = deepcopy(model)
        model["use_scope"] = "project"
        for src in model["sources"]:
            src["kind"] = "local_calculation"
        if missing != "review":
            model["sources"].append(dict(kind="user_provided", reference="identity.json", sha256=identity_ref["sha256"]))
        return sign(network, model)

    with monkeypatch.context() as patch:
        patch.setattr(cycle, "build_network", bound_network)
        patch.setattr(cycle, "signed", bound_model)
        entry = second_model(directory, temperature, 160000, spec["feeds_bar"][0])
    if missing != "identity":
        entry["electronic_identity"] = identity_ref
    return entry


@pytest.mark.parametrize("change", ["same", "dft", "conventions", "identity", "review", "electronic_source", "method"])
def test_project_method_binding(tmp_path, runtime, monkeypatch, change):  # noqa: F811
    spec = request()
    spec["feeds_bar"] = spec["feeds_bar"][:1]
    spec["models"] = [project_model(tmp_path / "cold", monkeypatch, spec, 400, "PBE", "spin-polarized"),
                      project_model(tmp_path / "hot", monkeypatch, spec, 450, "RPBE" if change == "dft" else "PBE",
                                    "nonmagnetic" if change == "conventions" else "spin-polarized", missing=change)]
    path, digest = prepare(tmp_path, runtime, spec)
    a, b = scan.collect(path, digest)["points"]
    assert a["status"] == "AWAITING_APPROVAL", a["reason"]
    assert b["status"] == ("AWAITING_APPROVAL" if change == "same" else "UNQUALIFIED"), b["reason"]
    if change in ("dft", "conventions"):
        assert "Model family differs" in b["reason"]
    elif change != "same":
        assert "identity" in b["reason"] or "anchor" in b["reason"]


def test_collect_rechecks_historical_grid_from_snapshots(tmp_path, runtime):  # noqa: F811
    spec = request()
    spec["models"].append(second_model(tmp_path, 450, 160000, spec["feeds_bar"][0]))
    path, digest = prepare(tmp_path, runtime, spec)
    snapshot = path.parent / (spec["models"][1]["network"]["sha256"] + ".json")
    snapshot.write_bytes(b"{}")
    report = scan.collect(path, digest)
    assert [row["status"] for row in report["points"]] == ["AWAITING_APPROVAL"] * 2 + ["UNQUALIFIED"] * 2
    assert all("SHA-256" in row["reason"] for row in report["points"][2:])
    assert all(edge["delta"] is None for edge in report["comparisons"])


def test_missing_reference_cannot_promote_another_model(tmp_path, runtime, monkeypatch):  # noqa: F811
    spec = request()
    first = project_model(tmp_path / "first", monkeypatch, spec, 400, "PBE", "spin", missing="identity")
    second = project_model(tmp_path / "second", monkeypatch, spec, 450, "PBE", "spin")
    spec["models"] = [first, second]
    path, digest = prepare(tmp_path, runtime, spec)
    rows = scan.collect(path, digest)["points"]
    assert all(r["status"] == "UNQUALIFIED" and r["plan_sha256"] is None for r in rows)
    assert "Missing reviewed electronic method" in rows[0]["reason"]
    assert "designated reference identity is unavailable" in rows[-1]["reason"]


def test_legacy_plan_cannot_bypass_family_check(tmp_path, runtime, monkeypatch):  # noqa: F811
    spec = request()
    spec["feeds_bar"] = spec["feeds_bar"][:1]
    spec["models"] = [project_model(tmp_path / "first", monkeypatch, spec, 400, "PBE", "spin", missing="identity"),
                      project_model(tmp_path / "second", monkeypatch, spec, 450, "RPBE", "spin", missing="identity")]
    with monkeypatch.context() as old:
        old.setattr(scan, "family", lambda *args: "legacy-unchecked-family")
        path, digest = prepare(tmp_path, runtime, spec)
    assert all(p["plan_sha256"] and p["reason"] is None for p in point.read(path)["points"])
    result = scan.collect(path, digest)
    assert all(p["status"] == "UNQUALIFIED" and "identity" in p["reason"] for p in result["points"])
    assert result["comparisons"][0]["delta"] is None


def test_missing_surface_structure_anchor():
    n, d, c = cycle_model(with_network=True)
    del n["catalog"]["surfaces"][0]["structural_provenance"]
    with pytest.raises(ValueError, match="Missing verified structure identity"):
        scan.family(n, d, c)
