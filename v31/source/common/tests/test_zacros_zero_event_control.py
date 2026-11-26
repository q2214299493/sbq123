"""Independent checks of an offline benchmark. No subprocess or engine invocation."""
from collections import Counter
from decimal import Decimal
import json
import math
from pathlib import Path
import re
import shutil
import sys

import pytest

from scripts.artifact_io import sha256_file
from scripts.surface_kmc.oxide_control import main as render_cli, render
from scripts.surface_kmc import zero_event_review as gate

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "reports/multiphase/stage_b2_3_2_4"
NATIVE = STAGE / "native"
CORRECTED = ROOT / "reports/architecture_repair/stage_r2_3/native"
PRIOR = ROOT / "reports/multiphase/stage_b2_3_2_3/native"
PARAMS = STAGE / "control.json"
REF = json.loads((STAGE / "numerical_reference.json").read_bytes())


def fields(lines):
    return {k: v for k, *v in map(str.split, lines)}


def blocks(name, keyword):
    data = (NATIVE / name).read_text().split("\n" + keyword + " ")[1:]
    return {part.splitlines()[0]: part.split("\nend_" + keyword)[0].splitlines()[1:] for part in data}


def test_rebuild_and_preserve_immutable_sources():
    files, manifest = render(PARAMS, ROOT)
    assert manifest == json.loads((CORRECTED / "input_manifest.json").read_bytes())
    assert set(files) == {base + "_input.dat" for base in ("simulation", "lattice", "energetics", "mechanism", "state")}
    assert all((CORRECTED / k).read_bytes() == v and b"@" not in v for k, v in files.items())
    assert manifest["structural_manifest_sha256"] == sha256_file(PRIOR / "input_manifest.json")
    for name in ("lattice_input.dat", "state_input.dat"):
        assert files[name] == (PRIOR / name).read_bytes()
    plan = json.loads((STAGE / "execution_plan.json").read_bytes())
    assert plan["input_files_sha256"] == {name: sha256_file(NATIVE / name) for name in files}
    assert manifest["files_sha256"] == {name: sha256_file(CORRECTED / name) for name in files}
    assert {name for name in files if files[name] != (NATIVE / name).read_bytes()} == {
        "simulation_input.dat", "mechanism_input.dat", "energetics_input.dat",
    }
    assert plan["bound_artifacts_sha256"]["control.json"] == sha256_file(PARAMS)
    assert plan["bound_artifacts_sha256"]["numerical_reference.json"] == sha256_file(STAGE / "numerical_reference.json")
    assert plan["dynamic_execution"] is plan["production_eligible"] is False


def test_independent_initial_catalogue_and_cluster_ledger():
    lat = (NATIVE / "lattice_input.dat").read_text().splitlines()
    lattice = [r.split() for r in lat[lat.index("lattice_structure") + 1:lat.index("end_lattice_structure")]]
    types = {int(i): typ for i, x, y, typ, degree, *neighbors in lattice}
    edges = {(int(r[0]), int(j)) for r in lattice if r[3] == "acidA" for j in r[5:]}
    assert Counter(types.values()) == {"acidA": 4, "oxygenB": 3} and len(edges) == 6
    state = {}
    for entity, line in enumerate((NATIVE / "state_input.dat").read_text().splitlines()[1:-1], 1):
        directive, species, *nodes = line.split()
        assert directive == "seed_on_sites" and species == "CO2bridge*" and len(nodes) == 2
        for leg, node in enumerate(map(int, nodes), 1):
            assert node not in state
            state[node] = entity, leg
    seeds = {pair for pair in edges if all(x in state for x in pair)
             and state[pair[0]] == (state[pair[1]][0], 1) and state[pair[1]][1] == 2}
    free = {e for e in edges if state.keys().isdisjoint(e)}
    assert seeds == {(1, 5), (2, 6)} == set(map(tuple, REF["directions"]["desorption"]["ordered_pairs"]))
    assert free == {(3, 7), (4, 7)} == set(map(tuple, REF["directions"]["adsorption"]["ordered_pairs"]))
    assert len({e for e, leg in state.values()}) == REF["initial"]["molecules"] == 2
    mech = blocks("mechanism_input.dat", "step")
    assert set(mech) == {"adsorption", "desorption"}
    empty = ["1 * 1", "2 * 1"]
    occupied = ["1 CO2bridge* 1", "1 CO2bridge* 2"]
    for name, left, right in [("adsorption", empty, occupied), ("desorption", occupied, empty)]:
        m = mech[name]
        assert {"sites 2", "site_types acidA oxygenB", "neighboring 1-2"} <= set(m)
        assert m[m.index("initial") + 1:m.index("initial") + 3] == left
        assert m[m.index("final") + 1:m.index("final") + 3] == right
        assert fields(m)["prox_factor"] == ["0.5"]
    clusters = blocks("energetics_input.dat", "cluster")
    assert set(clusters) == {"acid_vacancy", "oxygen_vacancy", "ordered_bridge"}
    for k, s in [("acid_vacancy", "acidA"), ("oxygen_vacancy", "oxygenB")]:
        cluster = clusters[k]
        assert {"sites 1", "lattice_state", f"site_types {s}", "1 * 1", "graph_multiplicity 1"} <= set(cluster)
        assert float(fields(cluster)["cluster_eng"][0]) == 0
    bridge = clusters["ordered_bridge"]
    assert {"sites 2", "site_types acidA oxygenB", "neighboring 1-2", "graph_multiplicity 1"} <= set(bridge)
    assert bridge[bridge.index("lattice_state") + 1:bridge.index("lattice_state") + 3] == occupied
    energy = Decimal(fields(bridge)["cluster_eng"][0])
    for count, expected in [(2, REF["initial"]), (3, REF["directions"]["adsorption"]["after_one_event"]),
                            (1, REF["directions"]["desorption"]["after_one_event"])]:
        assert float(energy * count) == expected["lattice_energy_eV"]
        if count != 2:
            assert (4 - count, 3 - count) == (expected["vacant_acid"], expected["vacant_oxygen"])


def test_native_arrhenius_values_and_pressure_order(tmp_path):
    sim = fields((NATIVE / "simulation_input.dat").read_text().splitlines())
    assert (sim["temperature"], sim["pressure"], sim["gas_molar_fracs"]) == (["400"], ["1"], ["1"])
    assert (sim["gas_specs_names"], sim["gas_molec_weights"], sim["gas_energies"]) == (["CO2"], ["44.0096"], ["0"])
    assert sim["surf_specs_dent"] == ["2"] and sim["max_steps"] == ["0"] and sim["wall_time"] == ["15"]
    assert "debug_report_processes" in sim and "no_restart" not in sim
    kb = Decimal("8.314472") / Decimal("6.02214179e23") * Decimal("6.24150974e18")
    captured = {}
    for name, m in blocks("mechanism_input.dat", "step").items():
        row = fields(m)
        signed = int(row["gas_reacs_prods"][1])
        assert row["gas_reacs_prods"][0] == "CO2" and signed == (-1 if name == "adsorption" else 1)
        A, Ea = (Decimal(row[k][0]) for k in ("pre_expon", "activ_eng"))
        assert (A, Ea) == ((100000, Decimal("0.10")) if signed < 0 else (10**13, Decimal("0.50")))
        unpressurized = A * (-Ea / (kb * Decimal(sim["temperature"][0]))).exp()
        for x in (Decimal(1), Decimal("0.5")):
            p = Decimal(sim["pressure"][0]) * x
            result = float(unpressurized * (p if signed < 0 else 1))
            target = REF["directions"][name]["propensity_per_match_s_inv"]
            assert math.isclose(result, target * (float(x) if signed < 0 else 1), rel_tol=2e-14)
        captured[name] = 2 * float(unpressurized)
        assert math.isclose(captured[name], REF["directions"][name]["summed_propensity_s_inv"], rel_tol=2e-14)
    assert math.isclose(sum(captured.values()), REF["combined_initial_propensity_s_inv"], rel_tol=2e-14)
    assert REF["detailed_balance"] == "not_assessed" and REF["physical_equilibrium_constant"] is None
    # Non-unit pressure reveals accidental pre-multiplication which is invisible at one bar.
    data = json.loads(PARAMS.read_bytes())
    data["conditions"].update(CO2_mole_fraction=0.5, CO2_partial_pressure_bar=0.5)
    alternate = tmp_path / "pressure.json"
    alternate.write_text(json.dumps(data))
    new, _ = render(alternate, ROOT)
    assert b"gas_molar_fracs 0.5\n" in new["simulation_input.dat"]
    assert new["mechanism_input.dat"] == (CORRECTED / "mechanism_input.dat").read_bytes()


@pytest.mark.parametrize("field", ["unit", "pressure", "steps", "source", "mass", "energy", "fraction"])
def test_incompatible_control_does_not_render(tmp_path, field):
    d = json.loads(PARAMS.read_bytes())
    if field == "unit":
        d["events"]["adsorption"]["unit"] = "s^-1"
    elif field == "pressure":
        d["conditions"]["CO2_partial_pressure_bar"] = 100000
    elif field == "steps":
        d["execution"]["max_steps"] = 1
    elif field == "mass":
        d["gas"]["molecular_weight_amu"] = -1
    elif field == "energy":
        d["events"]["desorption"]["activation_energy_eV"] = "invalid"
    elif field == "fraction":
        d["conditions"].update(CO2_mole_fraction=2, CO2_partial_pressure_bar=2)
    else:
        d["archived_structure"]["graph_sha256"] = "f" * 64
    f = tmp_path / "control.json"
    f.write_text(json.dumps(d))
    with pytest.raises(ValueError):
        render(f, ROOT)


@pytest.fixture
def review(tmp_path, monkeypatch):
    stage = tmp_path / "stage"
    stage.mkdir()
    shutil.copytree(CORRECTED, stage / "native")
    for name in ("execution_plan.json", "numerical_reference.json", "control.json"):
        shutil.copyfile(STAGE / name, stage / name)
    # Bind this temporary test plan to the revised input. Never reuse the consumed approval.
    plan_file = stage / "execution_plan.json"
    plan = json.loads(plan_file.read_bytes())
    manifest = stage / "native/input_manifest.json"
    plan["bound_artifacts_sha256"]["native/input_manifest.json"] = sha256_file(manifest)
    plan["input_files_sha256"] = json.loads(manifest.read_bytes())["files_sha256"]
    plan_file.write_text(json.dumps(plan), encoding="utf-8")
    # No distributed binary is required in CI. Only the executable hash probe is stubbed.
    exe = tmp_path / "offline-test-binary"
    expected = json.loads((stage / "execution_plan.json").read_bytes())["engine"]["sha256"]
    monkeypatch.setattr(gate, "sha256_file", lambda p: expected if p == exe else sha256_file(p))
    return stage, exe


def test_request_is_pending_and_state_handoff_cannot_authorize(review, tmp_path):
    stage, exe = review
    request = gate.prepare_request(stage, ROOT, exe)
    historical = json.loads((STAGE / "approval_request.json").read_bytes())
    assert request["state_sha256"] != historical["state_sha256"]
    assert request["input_files_sha256"] != historical["input_files_sha256"]
    consumed = STAGE / "native_acceptance"
    approval = json.loads((consumed / "execution_approval.json").read_bytes())
    with pytest.raises(ValueError, match="stale"):
        gate.check_reviewed_action(stage, ROOT, exe, approval, consumed / approval["source_file"])
    assert request["state_sha256"] == sha256_file(stage / "execution_plan.json")
    assert request["ALLOWED_ACTIONS"] == [] and request["DECISION"] == "pending"
    source = tmp_path / "mock-review.txt"
    source.write_text("offline gate test")
    decision = dict(format="zacros-zero-event-approval/1", DECISION="approve", ALLOWED_ACTIONS=[gate.ACTION],
                    reviewer="fixture", dataset_id=request["dataset_id"], question_id=request["question_id"],
                    state_sha256=request["state_sha256"], source_sha256=sha256_file(source))
    for value in (request, dict(decision, format="state-handoff/1"), dict(decision, DECISION="reject"),
                  dict(decision, question_id="another task"), dict(decision, source_sha256="f" * 64)):
        with pytest.raises(PermissionError):
            gate.check_reviewed_action(stage, ROOT, exe, value, source)
    with pytest.raises(ValueError, match="stale"):
        gate.check_reviewed_action(stage, ROOT, exe, dict(decision, state_sha256="a" * 64), source)
    assert gate.check_reviewed_action(stage, ROOT, exe, decision, source) == decision


@pytest.mark.parametrize("changed", ["native/mechanism_input.dat", "native/restart.inf", "numerical_reference.json",
                                     "control.json", "execution_plan.json", "binary"])
def test_changed_input_or_budget_prevents_request(review, changed, tmp_path):
    stage, exe = review
    p = stage / changed
    if changed == "execution_plan.json":
        d = json.loads(p.read_bytes())
        d["limits"]["max_steps"] = 1
        p.write_text(json.dumps(d))
    elif changed == "binary":
        exe = tmp_path / "unexpected-executable"
        exe.write_bytes(b"test")
    else:
        with p.open("ab") as f:
            f.write(b" ")
    with pytest.raises(ValueError):
        gate.prepare_request(stage, ROOT, exe)


# Emitted subset of Zacros 4.0 str_is_real: a decimal point or an exponent is required.
REAL = re.compile(rb"[+-]?(?:[0-9]+\.[0-9]+(?:[eE][+-]?[0-9]+)?|[0-9]+[eE][+-]?[0-9]+)")
REAL_FIELDS = {b"temperature", b"pressure", b"gas_energies", b"gas_molar_fracs", b"gas_molec_weights",
               b"pre_expon", b"activ_eng", b"prox_factor", b"cluster_eng"}


def test_only_eight_invalid_real_tokens_changed():
    changed = Counter()
    for path in CORRECTED.glob("*.dat"):
        old = (NATIVE / path.name).read_bytes().splitlines()
        for before, after in zip(old, path.read_bytes().splitlines(), strict=True):
            key, *tokens = before.split()
            if key not in REAL_FIELDS:
                assert before == after
                continue
            field, *new = after.split()
            assert field == key
            for left, right in zip(tokens, new, strict=True):
                assert REAL.fullmatch(right)
                assert Decimal(left.decode()) == Decimal(right.decode())
                if not REAL.fullmatch(left):
                    changed[field] += 1
                else:
                    assert left == right
    assert changed == {b"temperature": 1, b"pressure": 1, b"gas_energies": 1, b"gas_molar_fracs": 1,
                       b"pre_expon": 2, b"cluster_eng": 2}


@pytest.mark.parametrize("literal", ["400", "400.0", "400.000", "1e-5", "1e13", "2.5e22"])
def test_real_token_round_trip(tmp_path, literal):
    data = PARAMS.read_text().replace('"temperature_K": 400,', '"temperature_K": ' + literal + ',')
    path = tmp_path / "control.json"
    path.write_text(data, encoding="utf-8")
    files, _ = render(path, ROOT)
    token = fields(files["simulation_input.dat"].decode().splitlines())["temperature"][0]
    assert REAL.fullmatch(token.encode()) and Decimal(token) == Decimal(literal)


@pytest.mark.parametrize("value", ["400", "bad", True, None, [], float("nan"), float("inf"), -float("inf"), 2**53+1])
def test_invalid_real_rejected(tmp_path, value):
    data = json.loads(PARAMS.read_bytes())
    data["conditions"]["temperature_K"] = value
    path = tmp_path / "control.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="temperature_K"):
        render(path, ROOT)


@pytest.mark.parametrize("section,key", [("execution", "max_steps"), ("execution", "random_seed"),
                                         ("energetics", "graph_multiplicity"), ("adsorption", "CO2_gas_stoichiometry")])
def test_integer_field_rejects_equal_float(tmp_path, section, key):
    data = json.loads(PARAMS.read_bytes())
    parent = data["events"][section] if section == "adsorption" else data[section]
    parent[key] = float(parent[key])
    path = tmp_path / "control.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        render(path, ROOT)


def test_cli_cannot_replace_a_previous_bundle(tmp_path, monkeypatch):
    destination = tmp_path / "new-inputs"
    monkeypatch.setattr(sys, "argv", ["oxide_control", str(PARAMS), str(destination), "--root", str(ROOT)])
    render_cli()
    before = {p.name: sha256_file(p) for p in destination.iterdir()}
    assert before == {p.name: sha256_file(p) for p in CORRECTED.iterdir()}
    with pytest.raises(FileExistsError):
        render_cli()
    assert before == {p.name: sha256_file(p) for p in destination.iterdir()}
