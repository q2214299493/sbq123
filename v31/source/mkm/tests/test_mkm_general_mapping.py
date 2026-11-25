"""Analytical equal-capacity, two-contact adsorption control. All native outputs are synthetic."""

from copy import deepcopy
from pathlib import Path
import math

import numpy as np
import pytest
from scipy.io import savemat
from scipy.optimize import brentq

from scripts.artifact_io import sha256_file, sha256_json, write_json_exclusive
from scripts.baseline_mkm.network_mapping import map_network, replay_general, replay_starts
from scripts.baseline_mkm.steady_states import fixed_config
from test_mkm_steady_states import POLICY
from test_mkm_normalization import bind_fixture, definition
from scripts.baseline_mkm.single_point import qualify
from scripts.baseline_mkm.mapping_scope import MappingBlocked, topology
from scripts.baseline_mkm.native import native_names, render, side
from scripts.kinetic_parameters.export import catkinas, zacros
from scripts.multiphase_contracts import read_unique_json
from scripts.kinetic_parameters.engine import MOLECULAR_ACTIVITY, generate
from scripts.reaction_network.builder import build_network
from test_kinetic_parameters import DIGEST, case, signed


@pytest.fixture
def two_contacts():
    # This fixture defines its own bound species and uses only the kinetic reference.
    parent, model = case(gas=True, barrier=1.1, structure_records=False)
    catalog = deepcopy(parent["catalog"])
    other = "second-contact"
    catalog["interfaces"].append(dict(catalog["interfaces"][0], interface_id=other))
    catalog["sites"].append(dict(catalog["sites"][1], site_id="other-B", interface_id=other))
    gas, resident = parent["species"][:2]
    species, reactions, parameters, reviews, models = [gas], [], [], [], []
    for rid, site, contact in [("one", "bridge-Cu", "junction"), ("two", "other-B", other)]:
        footprint = {"top-Ni": 2, site: 1}
        sid = "bound-" + rid
        species.append(dict(resident, species_id=sid, structure_id=sid, site_occupancy=footprint, interface_id=contact))
        r = dict(
            deepcopy(parent["reactions"][0]["definition"]),
            reaction_id=rid,
            ts_id="ts-" + rid,
            products={sid: 1},
            sites_consumed=footprint,
            required_sites=footprint,
            interface_id=contact,
        )
        p = dict(deepcopy(parent["parameter_sets"][0]), reaction_id=rid, parameter_set_id="p-" + rid)
        m = dict(deepcopy(model), reaction_id=rid, parameter_set_id="p-" + rid)
        for record in (p, m):
            record["standard_states"]["surface_activity_convention"] = MOLECULAR_ACTIVITY
        del m["local_event"]
        models.append(m)
        reactions.append(r)
        parameters.append(p)
        reviews.append(
            dict(
                reaction_id=rid, grade="A", structure_identity=r["ts_id"], assignment="synthetic mode", review_reference="software fixture"
            )
        )
    bundle = dict(catalog, schema_version="1.0.0", species=species, reactions=reactions, parameter_sets=parameters, runs=[])
    options = dict(ts_reviews=reviews, verified_hashes={DIGEST}, sources=parent["source_artifacts"])
    n = build_network(bundle, **options)
    decisions = [
        dict(
            subject_sha256=e["subject_sha256"],
            reaction_id=e["definition"]["reaction_id"],
            decision="accepted",
            reviewer="synthetic reviewer",
            reason="software fixture",
            reviewed_at="2026-01-01T00:00:00Z",
        )
        for e in n["reactions"]
    ]
    n = build_network(bundle, decisions=decisions, **options)
    d = generate(n, dict(network_version=n["network_version"], models=[signed(n, m)["models"][0] for m in models]))
    bar = parameters[0]["pressure_Pa"] / 1e5
    c = dict(
        dataset_version=d["dataset_version"],
        partial_pressure_bar={"H2-g": bar},
        catkinas=dict(
            aliases={"H2-g": "G", "bound-one": "B", "bound-two": "B"},
            MaxTime=3,
            MaxOdeTime=3,
            initial_coverages={"bound-one": 0.0625, "bound-two": 0.125},
        ),
    )
    return n, d, c


def test_native_text_and_independent_inventories(two_contacts):
    n, d, c = two_contacts
    files, report = map_network(n, d, c, general=True)
    assert not report["issues"], report
    text = files["INPUT_phase25.m"]
    assert "G + 2#1 + #2 <-> B#1#1#2" in text and "G + 2#1 + #3 <-> B#1#1#3" in text
    assert "Q1x1x2_B_INIT = 0.0625" in text and "Q1x1x3_B_INIT = 0.125" in text
    assert "Q1_v_INIT = 0.625" in text and "Q2_v_INIT = 0.9375" in text and "Q3_v_INIT = 0.875" in text
    assert {v["interface_id"] for v in report["mapping"]["reactions"].values()} == {"junction", "second-contact"}
    assert not report["execution_authorized"] and report["physical_tof_eligibility"] == "unavailable"
    with pytest.raises(ValueError, match="only for offline MKM"):
        zacros(d)
    table = deepcopy(catkinas(d))
    table["rows"][0]["standard_states"]["surface_activity_convention"] = "fractional site occupation"
    with pytest.raises(ValueError, match="reviewed molecular activity"):
        render(table, c, d, general=True)
    with pytest.raises(MappingBlocked):
        qualify(n, d, c)
    c["catkinas"]["initial_coverages"]["bound-one"] = 0.5
    assert not map_network(n, d, c, general=True)[0]


def test_synthetic_mat_reconstruction(two_contacts, tmp_path):
    n, d, c = two_contacts
    files, report = map_network(n, d, c, general=True)
    text = files["INPUT_phase25.m"]
    bar = c["partial_pressure_bar"]["H2-g"]
    kt = 1.380649e-23 * 400 / 1.602176634e-19
    K = math.exp(0.1 / kt)
    y = brentq(lambda q: K * bar * (1 - 4 * q) ** 2 * (1 - q) - q, 0, 0.25, xtol=1e-15)
    kf = 0.25 * 5e-20 * 1e5 / math.sqrt(2 * math.pi * 2 * 1.66053906892e-27 * 1.380649e-23 * 400) * math.exp(-1.1 / kt)
    kr = kf / K
    flux = kf * bar * (1 - 4 * y) ** 2 * (1 - y)
    ea = kt * math.log((1.380649e-23 * 400 / 6.62607015e-34) / kf)
    labels = ["Q1x1x2_B", "Q1x1x3_B", "Q1_v", "Q2_v", "Q3_v"]
    log = "Converged, return with the residue 0 Succeed!!\nCATKINAS is finished now\n" + text
    log += "[ x(1), P_G ]\nSpecies G(gas)\n" + "".join(f"[ y({i}), {s} ]\n" for i, s in enumerate(labels, 1))
    path, mat = tmp_path / "log1", tmp_path / "data1.mat"
    path.write_text(log, encoding="ascii")
    data = dict(
        y=[[y, y, 1 - 4 * y, 1 - y, 1 - y]],
        yInits=[[0.0625, 0.125, 0.625, 0.9375, 0.875]],
        params=[[bar]],
        kf=[[kf, kf]],
        kr=[[kr, kr]],
        R=np.array([[[flux, flux, 0], [flux, flux, 0]]]),
        Rnet=[[0.0, 0.0]],
        Rnets=[[0.0]],
        Eao=[[ea, ea]],
        Ean=[[ea, ea]],
        G0o=[[-0.1, -0.1]],
        G0n=[[-0.1, -0.1]],
    )
    savemat(mat, data)
    replay = replay_general(n, d, c, mat, path)
    result = replay["result"]
    assert set(replay["pathways"]["cross_phase_reactions"]) == {"one", "two"}
    assert replay["coverages"]["sites"]["top-Ni"]["occupied_fraction"] == pytest.approx(4 * y)
    assert replay["rates"]["reactions"][0]["forward_flux"] == pytest.approx(flux)
    assert result["tof_s_inverse"] is None
    for row in result["species"]:
        if row["phase"] == "surface":
            assert row["molecules_per_reference"] == pytest.approx(y)
            assert row["occupied_sites_per_reference"]["top-Ni"] == pytest.approx(2 * y)
    assert [row["occupied_fraction"] for row in result["sites"]] == pytest.approx([4 * y, y, y])
    members = [
        dict(
            run="first",
            initial_coverages=c["catkinas"]["initial_coverages"],
            mat=mat.name,
            log=path.name,
            mat_sha256=sha256_file(mat),
            log_sha256=sha256_file(path),
        )
    ]
    second = dict(c, catkinas=dict(c["catkinas"], initial_coverages={"bound-one": 0.0, "bound-two": 0.0}))
    files2, _ = map_network(n, d, second, general=True)
    mat2, log2 = tmp_path / "other.mat", tmp_path / "other.log"
    savemat(mat2, dict(data, yInits=[[0.0, 0.0, 1.0, 1.0, 1.0]]))
    log2.write_text(log.replace(text, files2["INPUT_phase25.m"]), encoding="ascii")
    members.append(
        dict(
            run="second",
            initial_coverages=second["catkinas"]["initial_coverages"],
            mat=mat2.name,
            log=log2.name,
            mat_sha256=sha256_file(mat2),
            log_sha256=sha256_file(log2),
        )
    )
    def bind(member, identity, native_text, name):
        record = dict(format="mkm-trajectory-execution/1", execution_id=identity, dataset_version=d["dataset_version"],
                      initial_coverages_sha256=sha256_json(member["initial_coverages"]),
                      native_input_sha256=sha256_file(native_text), mat_sha256=member["mat_sha256"], log_sha256=member["log_sha256"])
        receipt = write_json_exclusive(tmp_path / name, record)
        return dict(member, execution_record=name, execution_sha256=sha256_file(receipt))

    inputs = []
    for index, (member, text) in enumerate(zip(members, (text, files2["INPUT_phase25.m"]), strict=True)):
        native_input = tmp_path / f"input-{index}.m"
        native_input.write_bytes(text.encode("ascii"))
        inputs.append(native_input)
        members[index] = bind(member, f"fixture-{index}", native_input, f"execution-{index}.json")
    study = write_json_exclusive(
        tmp_path / "study.json",
        dict(members=members, tolerances=POLICY, fixed_config_sha256=fixed_config(c), dataset_version=d["dataset_version"]),
    )
    assert replay_starts(n, d, c, study)["root_partition"] == {"groups": [["first", "second"]], "distinct_observed_roots": 1}
    duplicate = dict(members[1], run="third", initial_coverages={"bound-one": 0, "bound-two": 0})
    repeated = write_json_exclusive(tmp_path / "repeated.json", dict(read_unique_json(study), members=[*members, duplicate]))
    with pytest.raises(ValueError, match="Distinct named runs and initial"):
        replay_starts(n, d, c, repeated)
    def reject_member(member, name, message):
        request = dict(read_unique_json(study), members=[members[0], member])
        other = write_json_exclusive(tmp_path / (name + ".json"), request)
        with pytest.raises(ValueError, match=message):
            replay_starts(n, d, c, other)

    reject_member(bind(members[1], "fixture-0", inputs[1], "duplicate-id.json"), "case-id", "Repeated execution")
    reused = dict(members[1], **{k: members[0][k] for k in ("mat", "log", "mat_sha256", "log_sha256")})
    reject_member(bind(reused, "other", inputs[1], "reuse.json"), "case-reuse", "Repeated MAT/log")
    reject_member(dict(members[1], log_sha256="0"*64), "case-output", "output hash")
    reject_member(dict(members[1], execution_sha256="0"*64), "case-receipt", "Execution record hash")
    reject_member(bind(members[1], "other", inputs[0], "wrong-input.json"), "case-input", "does not bind")
    data["y"][0][2] += 0.01
    savemat(mat, data)
    with pytest.raises(ValueError, match="site inventory"):
        replay_general(n, d, c, mat, path)


def test_residual_budgets_follow_incident_reactions_and_sites():
    from scripts.baseline_mkm.single_point_result import check_steady_state

    definitions = [dict(reaction_id=rid, reactants={a: 1}, products={b: 1},
                        sites_consumed={site: 1}, sites_released={})
                   for rid, a, b, site in [("fast", "A", "B", "X"), ("slow", "C", "D", "Y")]]
    reactions = [dict(reaction_id="fast", forward_flux=1e13, reverse_flux=1e13, net_flux=0.),
                 dict(reaction_id="slow", forward_flux=.02, reverse_flux=.01, net_flux=.01)]
    species = {s: {"composition": {"H": 1}} for s in "ABCD"}
    sources = dict(A=0., B=0., C=-.01, D=.01)
    with pytest.raises(ValueError, match="residual for C"):
        check_steady_state(sources, reactions, {}, species, definitions, gross_roundoff=True)
    # Independently exercise the vacancy check with supplied projected molecular sources held at zero.
    sources = dict.fromkeys(species, 0.)
    with pytest.raises(ValueError, match="vacancy source for Y"):
        check_steady_state(sources, reactions, {}, species, definitions, gross_roundoff=True)
    reactions[1].update(forward_flux=.01, net_flux=0.)
    _, _, molecular, sites = check_steady_state(sources, reactions, {}, species, definitions, gross_roundoff=True)
    assert molecular["A"] == sites["X"] == .03125
    assert molecular["C"] == sites["Y"] == 1e-12


def test_three_phase_coupling_and_bidentate_product():
    fixture = Path(__file__).parent / "fixtures/multiphase/cross_phase_three_phase.json"
    definition = read_unique_json(fixture)
    r = definition["reactions"][0]
    r["reversible"] = True
    network = build_network(definition)
    issues, forms = topology(network, general=True)
    assert issues == [] and forms == {"combine": ["cross_phase_elementary"]}
    sites = {"A-pool": 1, "B-pool": 2, "C-pool": 3}
    names = native_names(network["species"], {"left-He": "He", "right-Ne": "Ne", "on-third": "HeNe"}, sites, general=True)
    assert side(r["reactants"], r["sites_consumed"], names, sites, numbered=True) == "He#1 + Ne#2 + 2#3"
    assert side(r["products"], r["sites_released"], names, sites, numbered=True) == "HeNe#3#3 + #1 + #2"
    assert not map_network(network, general=True)[0]  # No rates were supplied.


def test_archived_general_replay():
    root = Path(__file__).resolve().parents[1]
    archive = root / "archive/v221_catkinas/nicu-v221-400k-001"
    n, d, c = [read_unique_json(archive / (name + ".json")) for name in ("network", "dataset", "configuration")]
    norm = root / "reports/multiphase/phase3_1/benchmark_normalization.json"
    raw = archive / "runtime/result_phase25"
    general, report = map_network(n, d, c, normalization_path=norm, general=True)
    assert report["issues"] == [] and report["native_input_bytes_match_archive"]
    assert general == map_network(n, d, c, normalization_path=norm)[0]
    record = replay_general(n, d, c, raw / "data1.mat", raw / "log1", normalization_path=norm)
    assert record["result"]["tof_s_inverse"] == pytest.approx(81.5127701616477, rel=1e-12)
    assert record["result"]["mean_tof_per_individual_site_s"] == pytest.approx(40.75638508082385, rel=1e-12)


def test_closed_multidentate_exchange(tmp_path):
    parent, model = case()
    r = parent["reactions"][0]["definition"]
    r["reaction_type"] = "cross_phase_elementary"
    p = parent["parameter_sets"][0]
    for record in (p, model):
        record["standard_states"]["surface_activity_convention"] = MOLECULAR_ACTIVITY
    del model["local_event"]
    bundle = dict(parent["catalog"], schema_version="1.0.0", species=parent["species"][1:], reactions=[r], parameter_sets=[p], runs=[])
    review = dict(
        reaction_id="ads", grade="A", structure_identity=r["ts_id"], assignment="synthetic mode", review_reference="software fixture"
    )
    options = dict(ts_reviews=[review], verified_hashes={DIGEST}, sources=parent["source_artifacts"])
    first = build_network(bundle, **options)
    decision = dict(
        subject_sha256=first["reactions"][0]["subject_sha256"],
        reaction_id="ads",
        decision="accepted",
        reviewer="synthetic reviewer",
        reason="software fixture",
        reviewed_at="2026-01-01T00:00:00Z",
    )
    n = build_network(bundle, decisions=[decision], **options)
    d = generate(n, signed(n, model))
    c = dict(
        dataset_version=d["dataset_version"],
        partial_pressure_bar={},
        catkinas=dict(
            aliases={"H2-top": "A", "H2-bridge": "B"}, MaxTime=3, MaxOdeTime=3, initial_coverages={"H2-top": 0.25, "H2-bridge": 0.25}
        ),
    )
    files, report = map_network(n, d, c, general=True)
    assert files, report["issues"]
    native = files["INPUT_phase25.m"]
    assert "A#1 + #2 <-> B#1#2" in native
    kt = 1.380649e-23 * 400 / 1.602176634e-19
    kf = 1.380649e-23 * 400 / 6.62607015e-34 * math.exp(-0.4 / kt)
    kr = kf * math.exp(-0.1 / kt)
    bound = brentq(lambda b: kf * (0.5 - b) * (1 - b) - kr * b, 0, 0.5, xtol=1e-15)
    flux = kr * bound
    labels = ["Q1_A", "Q1x2_B", "Q1_v", "Q2_v"]
    log = tmp_path / "log1"
    log.write_text(
        "Converged, return with the residue 0 Succeed!!\nCATKINAS is finished now\n"
        + native
        + "".join(f"[ y({i}), {symbol} ]\n" for i, symbol in enumerate(labels, 1)),
        encoding="ascii",
    )
    mat = tmp_path / "data1.mat"
    savemat(
        mat,
        dict(
            y=[[0.5 - bound, bound, 0.5, 1 - bound]],
            yInits=[[0.25, 0.25, 0.5, 0.75]],
            kf=[[kf]],
            kr=[[kr]],
            R=np.array([[[flux, flux, 0]]]),
            Rnet=[[0.0]],
            Eao=[[0.4]],
            Ean=[[0.4]],
            G0o=[[-0.1]],
            G0n=[[-0.1]],
        ),
    )
    result = replay_general(n, d, c, mat, log)
    assert result["quality"]["conserved_molecular_residual"] < 1e-12
    assert result["result"]["gas_net_production"] == {}
    assert result["pathways"]["cross_phase_reactions"] == ["ads"]
    assert sum(s["molecules_per_reference"] for s in result["result"]["species"]) == pytest.approx(0.5)


def test_unequal_normalization_blocks_native_input(two_contacts, tmp_path):
    network, old, cfg = two_contacts
    profile = bind_fixture(tmp_path, network, definition("other", {"top-Ni": 2, "bridge-Cu": 1, "other-B": 1}))
    models = []
    for row in old["reactions"]:
        m = {k: v for k, v in row["model"].items() if k != "scientific_review"}
        models.extend(signed(network, m)["models"])
    data = generate(network, dict(network_version=network["network_version"], models=models))
    files, report = map_network(network, data, dict(cfg, dataset_version=data["dataset_version"]), general=True, normalization_path=profile)
    assert not files
    assert len(report["issues"]) == 1 and "one site of each" in report["issues"][0]["reason"]


def test_contact_aliasing_requires_distinguishable_rates(two_contacts):
    from scripts.baseline_mkm.mapping_scope import general_domain

    n, _, _ = two_contacts
    r = n["reactions"][0]["definition"]
    entries = [s["definition"] for s in n["reactions"]] + [dict(r, reaction_id="duplicate", interface_id="second-contact")]
    index = {
        key: {s[field]: s for s in rows}
        for key, field, rows in [("species", "species_id", n["species"]), ("sites", "site_id", n["catalog"]["sites"])]
    }
    issues = general_domain(index, entries)
    assert len(issues) == 1 and "share a native equation" in issues[0]["reason"]
