"""Step 2 synthetic topology, event and local parameter tests. No native subprocess."""

from copy import deepcopy
import math

import pytest

from scripts.native_model import assemble
from scripts.native_validation import zac_readback
from scripts.surface_kmc.lattice import lattice
from scripts.surface_kmc.observations import history_frames
from scripts.kinetic_parameters.export import zacros as event_table
from scripts.thermochemistry.harmonic import KB
from test_kinetic_parameters import DIGEST, case, dataset
from test_native_model import model


def open_model(gas=True):
    data, config = model(gas=gas)
    c = config["zacros"]
    for k in ("cell_vectors_A", "repeat_cell", "cell_sites", "links", "reference_sites_per_cell"):
        del c[k]
    nodes = [
        dict(node_id=str(i), inventory_id="top-Ni" if i % 2 else "bridge-Cu", drawing_xy_angstrom=[i, 0])
        for i in range(1, 8)
    ]
    c.update(
        reference_sites=3,
        snapshot_every_events=1,
        explicit_graph=dict(
            boundary="finite_open", nodes=nodes, edges=[[str(i), str(i + 1), "junction"] for i in range(1, 7)]
        ),
    )
    return data, config


def test_explicit_max_coord_follows_graph_and_periodic_uses_translations():
    d, c = open_model()
    edges = c["zacros"]["explicit_graph"]["edges"]
    edges[4] = ["3", "6", "junction"]
    files, _ = assemble("zacros", d, c)
    lines = files["lattice_input.dat"].splitlines()
    assert "max_coord 3" in lines
    assert "3 3.0 0.0 Ni 3 2 4 6" in lines

    d, c = model()
    files, _ = assemble("zacros", d, c)
    lines = files["lattice_input.dat"].splitlines()
    assert lines[0] == "lattice periodic_cell" and "neighboring_structure" in lines
    assert not any(line.startswith("max_coord") for line in lines)


@pytest.mark.parametrize(
    "replacement", ["max_coord 1", "max_coord 3", "", "max_coord 2 1", "max_coord 2\nmax_coord 2"]
)
def test_explicit_readback_rejects_invalid_max_coord(replacement):
    d, c = open_model()
    files, manifest = assemble("zacros", d, c)
    lattice_text = files["lattice_input.dat"]
    assert "max_coord 2" in lattice_text.splitlines()
    files["lattice_input.dat"] = lattice_text.replace("max_coord 2\n", replacement + "\n")
    with pytest.raises(ValueError, match="max_coord"):
        zac_readback(files, event_table(d), manifest["validation"])


@pytest.mark.parametrize("row", ["2 2.0 0.0 Cu 1 1 3", "2 2.0 0.0 Cu 2 1"])
def test_explicit_correct_max_coord_still_checks_neighbor_records(row):
    d, c = open_model()
    files, manifest = assemble("zacros", d, c)
    files["lattice_input.dat"] = files["lattice_input.dat"].replace("2 2.0 0.0 Cu 2 1 3", row)
    with pytest.raises(ValueError, match="topology"):
        zac_readback(files, event_table(d), manifest["validation"])


def test_crosswalk_occupancy_and_geometry_round_trip():
    d, c = open_model()
    c["zacros"]["seeds"] = [["H2-bridge", [1, 2]], ["H2-bridge", [3, 4]]]
    files, m = assemble("zacros", d, c)
    mapping = m["validation"]
    walk = mapping["topology"]
    assert walk["capacities"] == {"top-Ni": 4, "bridge-Cu": 3}
    assert walk["edges"] == [[i, i + 1, "junction"] for i in range(1, 7)]
    assert [e["matching_events"] for e in mapping["event_checks"]] == [6, 6]
    assert "snapshots on event 1" in files["simulation_input.dat"]
    raw = b"Surface_Species: HCu* HNi*\nconfiguration 1 0 0.0 400.0 0.0\n1 1 1 1\n2 1 1 2\n3 2 1 1\n4 2 1 2\n5 3 0 1\n6 4 0 1\n7 5 0 1\n"

    def frames(blob):
        return list(history_frames(blob, walk, mapping, d, event_table(d)["events"]))

    (frame,) = frames(raw)
    assert frame["molecules"] == {"H2-bridge": 2}
    assert frame["coverage"] == {"top-Ni": 0.5, "bridge-Cu": 2 / 3}
    assert sum(p["count"] for p in frame["neighbor_pairs"]) == 6
    for a, b in [(b"2 1 1 2", b"2 1 1 1"), (b"4 2 1 2", b"4 2 2 2"), (b"7 5 0 1", b"")]:
        with pytest.raises(ValueError):
            frames(raw.replace(a, b))
    files["lattice_input.dat"] = files["lattice_input.dat"].replace("1 1.0 0.0", "1 0.0 0.0")
    with pytest.raises(ValueError, match="topology"):
        zac_readback(files, event_table(d), mapping)


@pytest.mark.parametrize(
    "mutation", ["contact", "duplicate", "unknown node", "duplicate node", "alias", "leg", "overlap"]
)
def test_reject_ambiguous_graph_or_seed(mutation):
    d, c = open_model()
    z = c["zacros"]
    g = z["explicit_graph"]
    if mutation == "contact":
        g["edges"][0][-1] = None
    elif mutation == "duplicate":
        g["edges"].append(["2", "1", "junction"])
    elif mutation == "unknown node":
        g["edges"][0][0] = "missing"
    elif mutation == "duplicate node":
        g["nodes"][-1]["node_id"] = "1"
    elif mutation == "alias":
        z["site_aliases"]["top-Ni"] = z["site_aliases"]["bridge-Cu"]
    elif mutation == "leg":
        z["seeds"] = [["H2-bridge", [2, 1]]]
    else:
        z["seeds"] = [["H2-bridge", [1, 2]], ["H2-bridge", [3, 2]]]
    with pytest.raises(ValueError):
        assemble("zacros", d, c)


def test_periodic_wrap_duplicate_images_and_isolated_node():
    d, c = model()
    z = c["zacros"]
    _, _, g = lattice(z, set(z["site_aliases"]))
    assert (0, 0, 1) in g[2, 0, 2]
    z["repeat_cell"] = [3, 2]
    with pytest.raises(ValueError, match="duplicate"):
        lattice(z, set(z["site_aliases"]))
    d, c = open_model()
    c["zacros"]["explicit_graph"]["nodes"].append(
        dict(node_id="isolated", inventory_id="top-Ni", drawing_xy_angstrom=[9, 0])
    )
    f, m = assemble("zacros", d, c)
    assert "8 9.0 0.0 Ni 0\n" in f["lattice_input.dat"]
    assert m["validation"]["topology"]["capacities"]["top-Ni"] == 5


def test_reviewed_local_environment_on_forward_and_reverse():
    n, m = case(gas=True)
    loc = m["local_event"]
    # On the seven-site path, four directed embeddings have a second Cu next to the Ni.
    loc["environment"] = dict(site_ids=["bridge-Cu"], state=[None], neighbors_zero_based=[[0, 2]])
    loc["patterns_per_reference_site"] = dict(forward=4 / 3, reverse=4 / 3)
    d = dataset(n, m)
    _, c = open_model()
    c["dataset_version"] = d["dataset_version"]
    f, v = assemble("zacros", d, c)
    assert [r["matching_events"] for r in v["validation"]["event_checks"]] == [4, 4]
    assert f["mechanism_input.dat"].count("neighboring 1-2 1-3") == 2
    a, b = event_table(d)["events"]
    assert a["initial"] == b["final"] and a["final"] == b["initial"]


@pytest.mark.parametrize("kind", ["bep", "linear_descriptor"])
def test_local_fit_reversible_rate_and_conditional_covariance(kind):
    n, m = case(gas=False, standard_pa=200000)
    base = dataset(n, m)
    r = base["reactions"][0]
    fit = dict(
        kind=kind,
        basis="isolated_activation_gibbs_eV",
        energy_reference_id=r["parameter_set"]["energy_reference_id"],
        temperature_K=400,
        pressure_Pa=r["parameter_set"]["pressure_Pa"],
        training_sha256=DIGEST,
        validation_sha256=DIGEST,
        axes=[
            dict(
                name="reaction_gibbs" if kind == "bep" else "binding",
                value_eV=-0.1,
                domain_eV=[-0.2, 0.2],
                source_sha256=DIGEST,
            )
        ],
        coefficients=[0.55, 0.5],
        coefficient_covariance=[[0.0004, 0], [0, 0.01]],
        residual_sigma_eV=0,
    )
    m["local_event"].update(coefficient_basis="isolated_reactants", barrier_fit=fit)
    d = dataset(n, m)
    _, c = model(gas=False)
    c["dataset_version"] = d["dataset_version"]
    f, _ = assemble("zacros", d, c)
    events = event_table(d)["events"]
    kf, kr = [e["pre_expon"] for e in events]
    assert float(f["mechanism_input.dat"].split("pre_expon ")[1].split()[0]) == kf
    assert kf / event_table(base)["events"][0]["pre_expon"] == pytest.approx(math.exp(-0.1 / (KB * 400)))
    assert math.log(kf / kr) == pytest.approx(0.1 / (KB * 400))
    assert events[0]["local_prediction"]["conditional_sigma_ln_k"] == pytest.approx(
        math.sqrt(0.0005) / (KB * 400)
    )
    fit["axes"][0]["domain_eV"] = [0, 1]
    with pytest.raises(ValueError, match="domain"):
        event_table(dataset(n, m))


def test_per_embedding_balance_and_interface_transfer_geometry():
    n, m = case(gas=False)
    bad = deepcopy(m)
    bad["local_event"]["patterns_per_reference_site"]["reverse"] = 1
    with pytest.raises(ValueError, match="Detailed balance"):
        event_table(dataset(n, bad))
    d, c = open_model(False)
    f, _ = assemble("zacros", d, c)
    assert "gas_reacs_prods" not in f["mechanism_input.dat"]
    assert "1 HNi* 1\n2 * 1\nfinal\n1 HCu* 1\n1 HCu* 2" in f["mechanism_input.dat"]


def test_local_detailed_balance_uses_gas_standard_and_energy_shift():
    n, m = case(gas=True, standard_pa=200000)
    base = dataset(n, m)
    f, r = event_table(base)["events"]
    delta = 0.04
    sample = dict(
        environment_id="unlike-neighbor",
        source_sha256=DIGEST,
        temperature_K=400,
        energetics_sha256=None,
        local_reaction_energy_shift_eV=delta,
        forward=dict(coefficient=f["pre_expon"] * math.exp(-delta / (KB * 400)), unit=f["unit"]),
        reverse=dict(coefficient=r["pre_expon"], unit=r["unit"]),
    )
    m["local_event"]["balance_observations"] = [sample]
    # Use an explicit cluster model identity for a nonzero local shift.
    from scripts.artifact_io import sha256_json

    sample["energetics_sha256"] = m["local_event"]["energetics_sha256"] = sha256_json(
        {"synthetic_environment": 1}
    )
    check = event_table(dataset(n, m))["environment_balance"]["ads"]["unlike-neighbor"]
    assert abs(check["log_ratio_residual"]) < 1e-10
    sample["forward"]["coefficient"] *= 2
    with pytest.raises(ValueError, match="local environment"):
        event_table(dataset(n, m))
