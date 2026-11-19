"""Native model contracts use synthetic reviewed Phase 2.4 data and never launch an engine."""
import json
from copy import deepcopy

import pytest

from scripts.artifact_io import sha256_bytes, sha256_json
from scripts.baseline_mkm.native import check_coverage_points, render as render_cat
from scripts.kinetic_parameters.export import catkinas, zacros
from scripts.native_model import assemble, publish, with_checkpoint
from scripts.native_validation import cat_readback, zac_readback
from test_kinetic_parameters import FIX, ROOT, case, dataset


def model(system="interface", gas="dissociative", **options):
    d = dataset(*case(system=system, gas=gas, **options))
    c = json.loads((FIX / "native_interface_config.json").read_bytes())
    c["dataset_version"] = d["dataset_version"]
    if system != "interface":
        for s in d["catalog"]["sites"]:
            c["zacros"]["site_aliases"][s["site_id"]] = s["site_type"].replace("-", "_")
        c["zacros"]["surface_aliases"] = {"H2-top": "HA", "H2-bridge": "HB"}
    return d, c


@pytest.mark.parametrize("system", ["interface", "oxide", "Fe110"])
def test_two_site_flux_cross_engine_and_project_vocabulary(system):
    d, c = model(system)
    snapshot = deepcopy((d, c))
    cat, cm = assemble("catkinas", d, c, catkinas(d))
    zac, zm = assemble("zacros", d, c, zacros(d))
    assert "(1): H2 + #1 + #2 <-> H#1 + H#2" in cat["INPUT_phase25.m"]
    assert cm["validation"]["site_indices"] == {"top-Ni": 1, "bridge-Cu": 2}
    assert cm["validation"]["native_text_readback"]["coefficients_round_trip"]
    assert zm["validation"]["gas_indices"] == {"H2-g": 1}
    assert zm["validation"]["surface_indices"] == {"H2-bridge": 1, "H2-top": 2}
    assert not cm["execution_authorized"] and not zm["execution_authorized"]
    f, r = zm["validation"]["event_checks"]
    assert (f["native_step"], r["native_step"]) == ("r1_forward", "r2_reverse")
    assert f["reference_sites"] == 9 and f["matching_events"] == 18
    assert f["coefficient"] == pytest.approx(531.2521662552351)
    assert f["matching_events"] * f["coefficient"] == pytest.approx(f["reference_sites"] * 1062.5043325104702)
    assert "gas_reacs_prods H2 -1" in zac["mechanism_input.dat"] and "gas_reacs_prods H2 1" in zac["mechanism_input.dat"]
    assert all(v in zac["lattice_input.dat"] for v in c["zacros"]["site_aliases"].values())
    assert (d, c) == snapshot


def test_multidentate_and_seed_footprint():
    d, c = model(gas=True)
    c["zacros"]["seeds"] = [["H2-bridge", [1, 2]]]
    files, _ = assemble("zacros", d, c)
    assert "1 HCu* 1\n1 HCu* 2" in files["mechanism_input.dat"]
    assert "seed_on_sites HCu* 1 2" in files["state_input.dat"]
    with pytest.raises(ValueError, match="multidentate"):
        assemble("catkinas", d, c)
    c["zacros"]["seeds"] *= 2
    with pytest.raises(ValueError, match="Overlapping"):
        assemble("zacros", d, c)


def test_one_way():
    d, c = model(reversible=False)
    files, _ = assemble("zacros", d, c)
    assert "step r1_forward" in files["mechanism_input.dat"] and "reverse" not in files["mechanism_input.dat"]
    with pytest.raises(ValueError, match="forward-only"):
        assemble("catkinas", d, c)


def test_two_row_equation_indices_preserve_approved_order():
    d, c = model()
    table = catkinas(d)
    second = deepcopy(table["rows"][0])
    second["reaction_id"] = "return"
    second["directions"]["forward"] = second["directions"]["reverse"]
    second["forward"], second["reverse"] = second["reverse"], second["forward"]
    pair = second["fixed_T_energy_input"]
    pair["Ea_eV"] -= pair["G0_eV"]
    pair["G0_eV"] *= -1
    table["rows"].append(second)
    files, mapping = render_cat(table, c, d)
    assert mapping["reaction_indices"] == {"ads": 1, "return": 2}
    assert cat_readback(files, table, mapping)["equation_count"] == 2
    table["rows"].reverse()
    with pytest.raises(ValueError, match="order"):
        cat_readback(files, table, mapping)


def test_fixed_coverage_requires_conservation_and_matching_initial_value():
    d, _ = model()
    rows = catkinas(d)["rows"]
    rows[0]["coverage_fractions"] = {"spectator": 0.25}
    check_coverage_points(rows, {"spectator": 0.25})
    with pytest.raises(ValueError, match="conserved"):
        check_coverage_points(rows, {"spectator": 0.24})
    rows[0]["coverage_fractions"] = {"H2-top": 0.25}
    with pytest.raises(ValueError, match="conserved"):
        check_coverage_points(rows, {"H2-top": 0.25})


def test_surface_step_with_no_gas_consumption():
    d, c = model(gas=False)
    files, _ = assemble("zacros", d, c)
    assert "gas_reacs_prods" not in files["mechanism_input.dat"]


@pytest.mark.parametrize("issue", ["pressure", "multiplicity", "links", "aliases", "cluster", "coverage", "version", "mass"])
def test_invalid_configuration(issue):
    d, c = model()
    z = c["zacros"]
    engine = "zacros"
    if issue == "pressure":
        c["partial_pressure_bar"]["H2-g"] = 1e5
    elif issue == "multiplicity":
        z["reference_sites_per_cell"] = 2
    elif issue == "links":
        z["links"].append(z["links"][0])
    elif issue == "aliases":
        z["site_aliases"].pop("top-Ni")
    elif issue == "cluster":
        z["clusters"] = [{"energy_eV": 0.07}]
    elif issue == "coverage":
        c["catkinas"]["initial_coverages"]["H2-top"] = 1.01
        engine = "catkinas"
    elif issue == "mass":
        z["gas"]["H2-g"]["mass_g_mol"] = 4.0
    else:
        c["dataset_version"] = "wrong"
    with pytest.raises(ValueError):
        assemble(engine, d, c)


def test_bound_cluster_energetics():
    n, m = case(gas="dissociative")
    _, c = model()
    clusters = [{"site_ids": ["top-Ni", "bridge-Cu"], "neighbors_zero_based": [[0, 1]],
                 "state": [["H2-top", 1], ["H2-bridge", 2]], "energy_eV": 0.04, "graph_multiplicity": 1}]
    m["local_event"]["energetics_sha256"] = sha256_json({"clusters": clusters, "gas_energies_eV": {"H2-g": 0}})
    m["local_event"].update(coefficient_basis="isolated_reactants", forward_proximity_factor=0.25)
    d = dataset(n, m)
    c["zacros"]["clusters"] = clusters
    c["dataset_version"] = d["dataset_version"]
    files, _ = assemble("zacros", d, c)
    assert "cluster_eng 0.04" in files["energetics_input.dat"]
    assert [float(line.split()[1]) for line in files["mechanism_input.dat"].splitlines() if line.startswith("prox_factor")] == [0.25, 0.75]
    clusters[0]["energy_eV"] = 0.08
    with pytest.raises(ValueError, match="bound"):
        assemble("zacros", d, c)


@pytest.mark.parametrize("engine,file,source,mutation", [
    ("catkinas", "INPUT_phase25.m", "(1)", "(2)"),
    ("catkinas", "INPUT_phase25.m", "H#2", "H#1"),
    ("catkinas", "INPUT_phase25.m", "BarrierMode = -2", "BarrierMode = 0"),
    ("zacros", "mechanism_input.dat", "1-2", "1-3"),
    ("zacros", "mechanism_input.dat", "2 HCu* 1", "1 HCu* 1"),
    ("zacros", "mechanism_input.dat", "H2 -1", "H2 -2"),
    ("zacros", "simulation_input.dat", "pressure 1.", "pressure 2."),
])
def test_native_text_readback_rejects_mutation(engine, file, source, mutation):
    d, c = model()
    files, m = assemble(engine, d, c)
    assert source in files[file]
    files[file] = files[file].replace(source, mutation)
    exporter, check = (catkinas, cat_readback) if engine == "catkinas" else (zacros, zac_readback)
    with pytest.raises(ValueError):
        check(files, exporter(d), m["validation"])


@pytest.mark.parametrize("engine", ["catkinas", "zacros"])
def test_immutable_bundles_and_approved_tables(engine, tmp_path):
    d, c = model(standard_pa=200000)
    files, manifest = assemble(engine, d, c)
    dest = tmp_path / engine
    publish(dest, files, manifest)
    assert assemble(engine, d, dict(reversed(c.items()))) == (files, manifest)
    publish(dest, files, manifest)
    (dest / next(iter(files))).write_bytes(b"custom")
    with pytest.raises(ValueError, match="differs"):
        publish(dest, files, manifest)
    with pytest.raises(ValueError, match="Supplied table"):
        assemble(engine, d, c, {})


def test_restart_preserves_opaque_bytes_and_binds_model(tmp_path):
    d, c = model()
    c["zacros"]["write_restart"] = True
    f, m = assemble("zacros", d, c)
    raw = b"\x00\xffcheckpoint\r\n"
    receipt = {"model_sha256": sha256_json(m), "checkpoint_sha256": sha256_bytes(raw)}
    publish(tmp_path / "resume", *with_checkpoint(f, m, raw, receipt))
    assert (tmp_path / "resume" / "restart.inf").read_bytes() == raw
    with pytest.raises(ValueError, match="receipt"):
        with_checkpoint(f, m, raw + b"!", receipt)
    c["zacros"]["write_restart"] = False
    with pytest.raises(ValueError, match="enabled"):
        with_checkpoint(*assemble("zacros", d, c), raw, receipt)


@pytest.mark.parametrize("engine", ["catkinas", "zacros"])
def test_real_fe_blocked_before_configuration(engine):
    path = ROOT / "reports/multiphase/phase2_4/fe110_parameters.json"
    before = path.read_bytes()
    with pytest.raises(ValueError, match="blocked"):
        assemble(engine, json.loads(before), {})
    assert before == path.read_bytes()


@pytest.mark.parametrize("engine", ["catkinas", "zacros"])
def test_distributed_inputs_reproduce_native_smoke_model(engine):
    reports = ROOT / "reports/multiphase"
    c = json.loads((FIX / "native_interface_config.json").read_bytes())
    def load(name):
        return json.loads((reports / "phase2_4" / f"synthetic_interface_{name}.json").read_bytes())
    files, manifest = assemble(engine, load("dataset"), c, load(engine))
    bundle = reports / "phase2_5" / engine
    assert manifest == json.loads((bundle / "manifest.json").read_bytes())
    assert all((bundle / path).read_bytes() == value.encode() for path, value in files.items())
