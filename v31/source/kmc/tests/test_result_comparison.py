"""Analytical matched projections and separate checks at the two owning replay boundaries."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.artifact_io import sha256_file, sha256_json
from scripts.kinetic_data import result_comparison as comparison
from scripts.kinetic_data.comparison_observables import difference, measure
from scripts.kinetic_data.scientific_identity import dataset_reference, require_reaction_identity
from scripts.kinetic_parameters.rate_normalization import basis_identity
from scripts.surface_kmc import study

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports/workflow_development"
EXAMPLE = REPORTS / "stage_v3_1_step2_kmc_window_bridge/synthetic-example"
HIST = REPORTS / "stage_v3_1_step1_identity_binding"
QUERIES = [
    dict(kind="coverage", species="H2-bridge", inventory="top-Ni"),
    dict(kind="reaction_rate", reaction="ads", direction="forward"),
    dict(kind="site_utilization", inventory="bridge-Cu"),
    dict(kind="molecular_population", species="H2-bridge"),
]


def read(path):
    return json.loads(path.read_bytes())


def ref(path):
    return dict(path=str(path), sha256=sha256_file(path))


def write(path, doc):
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return ref(path)


def analytical(root):
    """Two simulated seconds, ten exchanges each way, four molecule-seconds, nine pairs."""
    ds_path = EXAMPLE / "mock-child-frozen/dataset.json"
    ds = read(ds_path)
    # The historical numerical oracle has no molecular structure records.
    structures = ROOT / "tests/fixtures/multiphase/h2_structure_records.json"
    for species in ds["species"]:
        species["structural_provenance"] = ref(structures)
    ds["dataset_version"] = sha256_json({k: v for k, v in ds.items() if k != "dataset_version"})
    source = dataset_reference(ds, write(root / "analytical-dataset.json", ds)["sha256"])
    standard = ds["reactions"][0]["parameter_set"]["standard_states"]
    conditions = dict(temperature_K=400, pressure_Pa=100000, partial_pressures=[dict(species_id="H2-g", pressure_Pa=100000)])
    sites = dict.fromkeys(["top-Ni", "bridge-Cu"], 1)
    scope = {k: ds[k] for k in ("project_id", "network_version")}
    base = dict(reference_scope=scope, extent_unit="event", time_unit="s", denominator_value=1)
    pair = dict(base, basis_kind="reference_site_pair", denominator_unit="reference site pair", reference_id="pair",
                definition="One site of each inventory", inventory_ids=sorted(sites))
    cell = dict(base, basis_kind="simulation_cell", denominator_unit="simulation cell", reference_id="nine-pairs",
                definition="Entire synthetic cell of nine pairs")
    def rate(basis, value):
        return dict(native_normalization=basis, conditions=conditions, provenance={"scope": "analytical fixture"},
                    output_binding=dict(dataset_id=sha256_json([basis, value])),
                    reaction_rates=[dict(reaction_id="ads", forward=value, reverse=value, net=0)])
    p = dict(root=dict(coverage={"H2-bridge": 0.2}, vacancy=dict.fromkeys(sites, 0.8),
                       analysis_residual=0, single_point_residual=0), run_id="analytical-point",
             conditions=dict(temperature_K=400, total_pressure_bar=1, partial_pressures_bar={"H2-g": 1}, standard_states=standard),
             dataset=source, normalization=dict(sites_per_reference=sites), input_hashes={"dataset": source["file_sha256"]},
             execution={key: sha256_json(["analytic", key]) for key in ("receipt_sha256", "mat_sha256", "log_sha256")})
    p["root_state_sha256"] = sha256_json(p["root"])
    p["binding_sha256"] = sha256_json(p)
    point = dict(binding=p, rate_output=rate(pair, 0.5), observations=dict(
        sites=[dict(site_id=s, occupied_fraction=0.2, vacancy_fraction=0.8, inventory=1) for s in sites],
        sites_per_molecular_reference={"pair": sites},
        species=[dict(species_id="H2-bridge", phase="surface", site_occupancy=sites, coverage=0.2,
                      molecules_per_reference=0.2, molecular_reference="pair")]))
    w = dict(conditions=dict(temperature_K=400, pressure_Pa=100000, partial_pressure_bar={"H2-g": 1}, standard_states=standard),
             definition=dict(bounds_s=[0, 2], event_interval="(start,end]", population_rule="left_held",
                             basis="simulation_cell", denominator=1), seed=123, checkpoint_lineage=[{"fixture": "single segment"}],
             configuration_sha256=sha256_json("analytical configuration"), result={"fixture": "analytical window"},
             dataset=source, reaction_network={"network_version": ds["network_version"]}, site_capacities=dict.fromkeys(sites, 9))
    w["window_evidence_sha256"] = sha256_json(w)
    kmc = dict(window=w, rate_output=rate(cell, 5), manifest_sha256=sha256_json("analytical evidence"),
               sampled_spans_s=dict.fromkeys(("specnum", "procstat"), [0, 2]),
               statistics=dict(independent_trajectories=1, effective_sample_size=None, confidence_interval=None),
               observations=dict(mean_molecules_per_cell={"H2-bridge": 2},
                                 time_weighted_occupied_fraction_by_species={s: {"H2-bridge": 2/9} for s in sites},
                                 time_weighted_site_utilization={s: dict(occupied_fraction=2/9, vacancy_fraction=7/9)
                                                                for s in sites}))
    kmc["record_sha256"] = sha256_json(kmc)
    review = dict(format="mkm-kmc-comparison-review/1", reviewer="analytical test fixture",
                  scope="synthetic_control", target="matched_stationary_ensemble", observables=QUERIES,
                  assessment="Constructed common stationary target for a numerical unit test.",
                  ensemble_evidence=write(root/"control.json", dict(duration_s=2, exchanges_each_way=10,
                                                                   molecule_seconds=4, pairs=9, scope="analytical fixture")),
                  parameter_sources=[ref(ROOT/"tests/fixtures/multiphase/kinetic_reference.json")],
                  mkm_binding_sha256=p["binding_sha256"], kmc_record_sha256=kmc["record_sha256"],
                  mapping=dict(quantity="references_per_cell", value=9, unit="1", numerator_basis_sha256=basis_identity(pair),
                               denominator_basis_sha256=basis_identity(cell)))
    return point, kmc, ds, review


@pytest.fixture
def control(tmp_path, monkeypatch):
    point, kmc, ds, review = analytical(tmp_path)
    right = deepcopy(ds)
    monkeypatch.setattr(comparison, "_point", lambda *args: (point, ds))
    monkeypatch.setattr(comparison, "_window", lambda *args: (kmc, right))
    def run(queries=QUERIES):
        request = dict(format="mkm-kmc-comparison/1", mkm={"fixture": "analytic"}, kmc={"fixture": "analytic"},
                       review=write(tmp_path/"review.json", review), observables=queries)
        f = write(tmp_path/"request.json", request)
        return comparison.compare(f["path"], f["sha256"], mkm_worktree=None)
    return run, point, kmc, right, review


def test_four_matched_observables(control):
    run, *_ = control
    result = run()
    for row, expected in zip(result["comparisons"], [1/45, 1/18, 1/45, 1/45], strict=True):
        assert row["difference"]["absolute"] == pytest.approx(expected), row["reasons"]
        assert row["difference"]["relative_to_abs_mkm"] == pytest.approx(1/9)
        assert row["compatibility"].startswith("comparable")
    assert result["comparisons"][1]["kmc"]["value"] == 5
    assert result["comparisons"][3]["kmc"]["value"] == 2
    assert result["uncertainty"]["difference_interval"] is None
    assert result == run()


@pytest.mark.parametrize("fault,reason", [
    ("pressure", "gas conditions"), ("energy", "energy_reference"), ("root", "root evidence"),
    ("event", "event-time"), ("provenance", "parameter source"), ("normalization", "multiplicity"),
    ("basis", "physical bases"), ("omit", "references_per_cell"), ("scope", "absent from ensemble"),
    ("review", "another point"), ("species", "molecular"), ("direction", "Unsupported rate direction"),
])
def test_ineligible(control, fault, reason):
    run, point, kmc, ds, review = control
    q = deepcopy(QUERIES[1])
    if fault == "pressure":
        kmc["window"]["conditions"]["partial_pressure_bar"]["H2-g"] = 0.9
    elif fault == "energy":
        ds["reactions"][0]["parameter_set"]["energy_reference_id"] = "different"
        ds["dataset_version"] = sha256_json({k: v for k, v in ds.items() if k != "dataset_version"})
    elif fault == "root":
        point["binding"]["root"]["coverage"] = {}
    elif fault == "event":
        del kmc["sampled_spans_s"]["procstat"]
    elif fault == "provenance":
        review["parameter_sources"] = []
    elif fault == "normalization":
        review["mapping"]["value"] = 8
    elif fault == "basis":
        review["mapping"]["denominator_basis_sha256"] = "0" * 64
    elif fault == "omit":
        del review["mapping"]
    elif fault == "scope":
        review["observables"] = [QUERIES[0]]
    elif fault == "review":
        review["kmc_record_sha256"] = "1" * 64
    elif fault == "species":
        ds.update(read(Path(read(HIST/"ads-counterexample.json")["mkm"]["path"])))
    elif fault == "direction":
        q["direction"] = "gross"
    row, = run([q])["comparisons"]
    assert row["difference"] is None and row["conversion"] is None
    assert reason in str(row["reasons"])
    if fault in ("omit", "normalization", "basis"):
        assert row["compatibility"] == ("not_comparable" if fault == "normalization" else "insufficient_evidence")
        assert run([QUERIES[0]])["comparisons"][0]["compatibility"] == "comparable"


def test_decimal_pressure_equivalence_and_neighbors(tmp_path):
    from scripts.kinetic_data.native_rate_output import conditions_pa
    point, kmc, data, _ = analytical(tmp_path)
    bar, pa = 1.00002, 100002
    partials = {"H2-g": bar}
    point["binding"]["conditions"].update(total_pressure_bar=bar, partial_pressures_bar=partials)
    wc = kmc["window"]["conditions"]
    wc.update(pressure_Pa=pa, partial_pressure_bar=partials)
    for record in (point, kmc):
        record["rate_output"]["conditions"] = conditions_pa(400, bar, partials)
    for reaction in data["reactions"]:
        reaction["parameter_set"]["pressure_Pa"] = pa
    data["dataset_version"] = sha256_json({k: v for k, v in data.items() if k != "dataset_version"})
    comparison._common(point, kmc, data, data)
    wc["pressure_Pa"] = 100002.000000001
    with pytest.raises(ValueError, match="gas conditions"):
        comparison._common(point, kmc, data, data)


def test_equal_values_different_windows(control):
    run, _, kmc, _, review = control
    first = run()
    w = kmc["window"]
    w["definition"]["bounds_s"] = [2, 4]
    w["window_evidence_sha256"] = sha256_json(w["definition"])
    kmc["record_sha256"] = review["kmc_record_sha256"] = sha256_json(w)
    second = run()
    assert first["comparisons"] == second["comparisons"]
    assert first["comparison_sha256"] != second["comparison_sha256"]


def test_historical_receipt_and_event_window_through_public_reader(tmp_path, monkeypatch):
    cases = read(HIST/"ads-counterexample.json")
    original = [read(Path(cases[k]["path"])) for k in ("mkm", "kmc")]
    with pytest.raises(ValueError, match="molecular_stoichiometry"):
        require_reaction_identity(*original, "ads")
    run = Path(cases["mkm"]["path"]).parent
    install = next(d for d in run.parents if (d/"scripts/kinetic_data/comparison_point.py").exists())
    monkeypatch.setattr(study, "ENGINE", sha256_file(EXAMPLE/"inert-file"))
    m = dict(run=str(run), binding_sha256=read(HIST/"mkm-point.json")["binding_sha256"])
    request = dict(format="mkm-kmc-comparison/1", mkm=m, kmc=ref(EXAMPLE/"manifest-0.25-5.25.json"),
                   observables=[QUERIES[1]])
    f = write(tmp_path/"request.json", request)
    res = comparison.compare(f["path"], f["sha256"], mkm_worktree=install)
    row, = res["comparisons"]
    assert row["difference"] is None and "molecular_stoichiometry" in str(row["reasons"])
    assert row["mkm"]["value"] > 90 and row["kmc"]["value"] == pytest.approx(3/5)
    assert res["evidence"]["mkm"]["binding_sha256"] == m["binding_sha256"]
    assert len(res["evidence"]["kmc"]["lineage"]) == 2


def test_turnover_selectivity_and_undefined_cases(control):
    run, point, kmc, ds, review = control
    # Isolate derived definitions using balanced sources for isomers A, B, C.
    gases = [dict(species_id=s, phase="gas") for s in ("A", "B", "C")]
    dataset = dict(species=gases)
    overall = {"A": -4, "B": 3, "C": 1}
    tof = dict(kind="tof", overall_stoichiometry=overall)
    selectivity = dict(kind="selectivity", products=["B", "C"], species="B")
    for record, mk, scale in ((point, True, 1), (kmc, False, 9)):
        sources = [dict(species_id=s, net_production_rate=n*scale) for s, n in overall.items()]
        record["rate_output"]["source_terms"] = dict(species=sources)
        if mk:
            record["observations"].update(total_reaction=overall, tof_s_inverse=1, molar_selectivity={"B": 0.75, "C": 0.25})
        else:
            record["rate_output"]["reaction_rates"] = [
                dict(reaction_id="productive", reactants={"A": 4}, products={"B": 3, "C": 1}, sites_consumed={}, sites_released={})]
            record["window"]["observation"] = dict(pathway_flux={"productive": dict(forward=20, reverse=2)})
        assert measure(tof, record, dataset, mkm=mk)["value"] == scale
        assert measure(selectivity, record, dataset, mkm=mk)["value"] == 0.75
        if not mk:
            for request in (tof, selectivity):
                left = measure(request, point, dataset, mkm=True)
                right = measure(request, kmc, dataset, mkm=False)
                diff, _ = difference(request, left, right, review["mapping"], point["binding"], kmc["window"])
                assert diff["absolute"] == 0
        with pytest.raises(ValueError, match="Competing"):
            measure(dict(selectivity, products=["B"]), record, dataset, mkm=mk)
        prior = [s["net_production_rate"] for s in sources]
        for s in sources:
            s["net_production_rate"] = 0
        if not mk:
            record["window"]["observation"]["pathway_flux"]["productive"]["forward"] = 2
        with pytest.raises(ValueError, match="Zero positive"):
            measure(selectivity, record, dataset, mkm=mk)
        with pytest.raises(ValueError, match="No observed net cycle"):
            measure(tof, record, dataset, mkm=mk)
        for s, value in zip(sources, prior, strict=True):
            s["net_production_rate"] = value


def test_failed_replay_preserves_verified_counterpart(tmp_path, monkeypatch):
    monkeypatch.setattr(study, "ENGINE", sha256_file(EXAMPLE/"inert-file"))
    install = Path(read(HIST/"ads-counterexample.json")["mkm"]["path"]).parents[4]
    request = dict(format="mkm-kmc-comparison/1", mkm=dict(run="absent", binding_sha256="0"*64),
                   kmc=ref(EXAMPLE/"manifest-0.25-5.25.json"), observables=[QUERIES[1]])
    f = write(tmp_path/"request.json", request)
    result = comparison.compare(f["path"], f["sha256"], mkm_worktree=install)
    row, = result["comparisons"]
    assert row["mkm"] is None and row["kmc"]["value"] == 0.6 and row["difference"] is None
    assert "MKM replay failed" in str(row["reasons"])
    with pytest.raises(ValueError, match="Unverified comparison request"):
        comparison.compare(f["path"], "0"*64, mkm_worktree=install)


def test_zero_reference_and_reported_confidence(control):
    run, point, kmc, _, review = control
    point["rate_output"]["reaction_rates"][0]["net"] = 0
    request = dict(kind="reaction_rate", reaction="ads", direction="net")
    review["observables"] = [request]
    review["uncertainty"] = {"fixture_interval": [0, 0.1], "unit": "events per pair per s"}
    result = run([request])
    row, = result["comparisons"]
    assert row["difference"]["absolute"] == 0 and row["difference"]["relative_to_abs_mkm"] is None
    assert result["uncertainty"]["reviewed"] == review["uncertainty"]
    assert result["uncertainty"]["difference_interval"] is None


def test_one_residual_surface_molecule_disqualifies_long_window_turnover(control):
    _, _, kmc, _, _ = control
    # Gas coefficients match the requested catalyst cycle, but the measured surface is still changing.
    kmc["window"]["definition"]["bounds_s"] = [0, 1e15]
    rows = [
        dict(reaction_id="productive", reactants={"A": 1}, products={"B": 1}, sites_consumed={}, sites_released={}),
        dict(reaction_id="transfer", reactants={"X": 1}, products={"Y": 1}, sites_consumed={}, sites_released={})]
    kmc["rate_output"]["reaction_rates"] = rows
    kmc["window"]["observation"] = dict(pathway_flux={r["reaction_id"]: {"forward": 1, "reverse": 0} for r in rows})
    with pytest.raises(ValueError, match="Surface accumulation"):
        measure(dict(kind="tof", overall_stoichiometry={"A": -1, "B": 1}), kmc,
                dict(species=[dict(species_id=s, phase="gas") for s in "AB"]), mkm=False)


@pytest.mark.parametrize("case,status,reason", [
    ("unique", "comparable_after_explicit_conversion", None),
    ("other", "not_comparable", "molecular_stoichiometry"),
    ("absent", "insufficient_evidence", "matched 0 records"),
    ("duplicate", "insufficient_evidence", "matched 2 records"),
    ("changed", "insufficient_evidence", "SHA-256 mismatch"),
    ("unreadable", "insufficient_evidence", "isomers.json"),
    ("unsupported", "insufficient_evidence", "Unsupported molecular structure"),
    ("rate_only", "insufficient_evidence", "Unsupported molecular structure payload"),
    ("bad_provenance", "insufficient_evidence", "structural_provenance"),
])
def test_loaded_structure_evidence(tmp_path, monkeypatch, case, status, reason):
    point, window, left, review = analytical(tmp_path)
    right = deepcopy(left)
    path = tmp_path / "isomers.json"
    records = [dict(id="cis", configuration="cis"), dict(id="trans", configuration="trans")]
    if case == "duplicate":
        records.append(dict(id="cis", configuration="trans"))
    if case == "rate_only":
        records = [dict(id="cis", rate_constant_s_inverse=123)]
    source = write(path, records if case != "unsupported" else 17)
    if case == "bad_provenance":
        source = [source]
    for ds in (left, right):
        sid = "absent" if case == "absent" else "trans" if ds is right and case == "other" else "cis"
        next(s for s in ds["species"] if s["phase"] == "gas").update(structure_id=sid, structural_provenance=source)
        ds["dataset_version"] = sha256_json({k: v for k, v in ds.items() if k != "dataset_version"})
    if case == "changed":
        path.write_bytes(path.read_bytes() + b" ")
    if case == "unreadable":
        source["path"] = str(tmp_path / "missing" / path.name)
        for ds in (left, right):
            ds["dataset_version"] = sha256_json({k: v for k, v in ds.items() if k != "dataset_version"})
    monkeypatch.setattr(comparison, "_point", lambda *args: (point, left))
    monkeypatch.setattr(comparison, "_window", lambda *args: (window, right))
    req = write(tmp_path / "request.json", dict(format="mkm-kmc-comparison/1", observables=[QUERIES[1]],
                review=write(tmp_path / "review.json", review), mkm={}, kmc={}))
    row, = comparison.compare(req["path"], req["sha256"], mkm_worktree=None)["comparisons"]
    assert row["compatibility"] == status
    if reason:
        assert reason in str(row["reasons"]) and row["difference"] is None
    else:
        assert row["difference"]["signed_kmc_minus_mkm"] == pytest.approx(1/18)


@pytest.mark.parametrize("entries,reason", [
    ([None], "[0] must be an object"), ([17], "[0] must be an object"),
    ([{}], "[0].reaction_id"), ({"ads": "reverse"}, "must be a list"),
    ([dict(reaction_id="ads", direction=[], surface_species="H2-bridge", gas_species="H2-g")], "[0].direction"),
    ([dict(reaction_id="missing", direction="reverse", surface_species="H2-bridge", gas_species="H2-g")],
     "unknown reaction"),
])
def test_invalid_mapping_keeps_window_measurements(tmp_path, monkeypatch, entries, reason):
    from scripts.surface_kmc.window_bridge import bridge
    manifest = read(EXAMPLE / "manifest-0.25-5.25.json")
    for item in manifest["artifacts"].values():
        item["path"] = str(EXAMPLE / item["path"])
    mapping = dict(format="kmc-intact-desorptions/1", network_sha256=manifest["artifacts"]["network"]["sha256"],
                   intact_desorptions=entries)
    manifest["artifacts"]["molecular_mapping"] = write(tmp_path / "mapping.json", mapping)
    kmc_ref = write(tmp_path / "manifest.json", manifest)
    monkeypatch.setattr(study, "ENGINE", sha256_file(EXAMPLE / "inert-file"))
    with pytest.raises(ValueError, match="Molecular mapping"):
        bridge(kmc_ref["path"], kmc_ref["sha256"])
    run = Path(read(HIST / "ads-counterexample.json")["mkm"]["path"]).parent
    install = next(p for p in run.parents if (p / "scripts/kinetic_data/comparison_point.py").exists())
    req = write(tmp_path / "request.json", dict(format="mkm-kmc-comparison/1", observables=[QUERIES[1]],
                mkm=dict(run=str(run), binding_sha256=read(HIST / "mkm-point.json")["binding_sha256"]), kmc=kmc_ref))
    result = comparison.compare(req["path"], req["sha256"], mkm_worktree=install)
    row, = result["comparisons"]
    assert row["compatibility"] == "insufficient_evidence" and row["difference"] is None
    assert reason in str(row["reasons"]) and row["kmc"]["value"] == 0.6
    values = result["evidence"]["kmc"]["residence_exposure_over_desorptions"]["H2-bridge"]
    assert (values["state_exits"], values["molecule_seconds"]) == (2, 2.25)
    assert values["molecular_desorptions"] is None and values["estimate_s"] is None
