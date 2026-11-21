"""Independent archive oracles for B.1. No production reader, rate calculator or source projector."""

import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pytest
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "reports/multiphase"
ARCH = BASE / "stage_b1_4"
ZACROS = BASE / "phase2_5_1"
NATIVE_CASES = ("mono", "dent", "full", "interacting", "attractive", "continuous", "split", "resume")


def read(path):
    return json.loads(path.read_bytes())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def output(engine, case):
    return read(ARCH / "replay" / f"{engine}-{case}.json")


def catkinas_oracle(case):
    path = BASE / case
    data = loadmat(path / "data1.mat")
    log = (path / "native_log_extract.txt").read_text(encoding="ascii")
    v = output("catkinas", case)
    assert digest((path / "data1.mat").read_bytes()) == v["provenance"]["native_output"]["sha256"]
    ids = ("ads", "transfer", "hydrogenate", "desorb")
    rates = {r["reaction_id"]: r for r in v["reaction_rates"]}
    pairs = {p["reaction_id"]: p for p in v["rate_coefficients"]}
    assert set(rates) == set(pairs) == set(ids)
    native_input = ROOT / v["output_binding"]["native_inputs"][0]["path"]
    text = native_input.read_text(encoding="ascii")
    equations = re.findall(r"^\(\d+\): (.*?) \[([^ ]+) ([^\]]+)\]", text, re.M)
    assert [eq for eq, _, _ in equations] == [
        "H2 + #1 + #2 <-> H#1 + H#2",
        "H#2 + #1 <-> H#1 + #2",
        "H#1 + NO <-> HNO#1",
        "HNO#1 <-> HNO + #1",
    ]

    def symbols(name, field):
        return {
            label: data[field][0, int(i) - 1] for i, label in re.findall(r"\[\s*" + name + r"\((\d+)\),\s*(\w+)", log)
        }

    y, p = symbols("y", "y"), symbols("x", "params")
    h, hc, hn = y["Q1_H"], y["Q2_H"], y["Q1_HNO"]
    vn, vc = y["Q1_v"], y["Q2_v"]
    np.testing.assert_allclose([h + hn + vn, hc + vc], 1, rtol=0, atol=1e-14)
    activity_f = np.array([p["P_H2"] * vn * vc, hc * vn, h * p["P_NO"], hn])
    activity_r = np.array([h * hc, h * vc, hn, p["P_HNO"] * vn])
    kf, kr = data["kf"][0], data["kr"][0]
    f, r = kf * activity_f, kr * activity_r
    native_f, native_r, native_net = data["R"][0].T
    inferred_f, inferred_r = native_f / activity_f, native_r / activity_r
    np.testing.assert_allclose([inferred_f, inferred_r], [kf, kr], rtol=2e-14, atol=0)
    np.testing.assert_allclose([f, r], [native_f, native_r], rtol=2e-14, atol=0)
    np.testing.assert_allclose(f - r, native_net, rtol=2e-14, atol=0)
    np.testing.assert_array_equal(native_net, data["Rnet"][0])

    # Independent SI Eyring estimate using the fixed-T native apparent barrier convention.
    T = float(re.search(r"^T = ([\d.]+);", text, re.M)[1])
    kbt = 1.380649e-23 * T
    ea, dg = np.array([[float(a), float(g)] for _, a, g in equations]).T
    theory = kbt / 6.62607015e-34 * np.exp(-ea * 1.602176634e-19 / kbt)
    theory_r = theory * np.exp(dg * 1.602176634e-19 / kbt)
    np.testing.assert_allclose([kf, kr], [theory, theory_r], rtol=1e-4, atol=0)
    observations = {}
    for i, rid in enumerate(ids):
        for direction, k, flux in (("forward", kf, f), ("reverse", kr, r)):
            assert pairs[rid][direction]["value"] == k[i]
            assert rates[rid][direction] == pytest.approx(flux[i], rel=2e-14)
        assert rates[rid]["net"] == native_net[i]
        observations[rid] = dict(
            kf_from_flux=float(inferred_f[i]),
            kr_from_flux=float(inferred_r[i]),
            forward_mass_action=float(f[i]),
            reverse_mass_action=float(r[i]),
            net_from_difference=float(f[i] - r[i]),
            native_net=float(native_net[i]),
            kf_Eyring=float(theory[i]),
            kr_Eyring=float(theory_r[i]),
        )
    a, t, g, d = map(float, native_net)
    species = {"H2-g": -a, "H2-top": a + t - g, "H2-bridge": a - t, "NO-g": -g, "HNO-top": g - d, "HNO-g": d}
    vacancy = {"top-Ni": -a - t + d, "bridge-Cu": -a + t}
    assert species == {row["species_id"]: row["net_production_rate"] for row in v["source_terms"]["species"]}
    assert vacancy == {row["site_id"]: row["net_vacancy_rate"] for row in v["source_terms"]["site_inventories"]}
    names = re.search(r"^Species\s+(.+)$", log, re.M)[1].split()
    assert all(
        species[name.removesuffix("(gas)") + "-g"] == value for name, value in zip(names, data["Rnets"][0], strict=True)
    )
    norm = read(BASE / "phase3_1/benchmark_normalization.json")
    assert norm["reference_basis"] == v["native_normalization"]["basis_kind"] == "reference_site_pair"
    assert norm["sites_per_reference"] == {"top-Ni": 1, "bridge-Cu": 1}
    assert a == t == d / 2 == g / 2 == 81.5127701616477
    mean = a / sum(norm["sites_per_reference"].values())
    assert mean == 40.75638508082385 and d == 163.0255403232954 and vacancy == dict.fromkeys(vacancy, 0)
    return dict(
        mat_sha256=v["provenance"]["native_output"]["sha256"],
        reactions=observations,
        species_per_pair_s=species,
        vacancies_per_pair_s=vacancy,
        turnover_per_pair_s=a,
        mean_per_site_s=mean,
    )


def physical_edges(raw):
    # Native lattice_output: site ID, x, y, site type, degree, followed by its neighbors.
    sites = {
        int(tokens[0]): (int(tokens[3]), set(map(int, tokens[5:])))
        for line in raw.decode().splitlines()
        if (tokens := line.split()) and int(tokens[0]) > 0
    }
    edges = {(i, j) for i, (kind, neighbors) in sites.items() if kind == 1 for j in neighbors if sites[j][0] == 2}
    assert all(i in sites[j][1] for i, j in edges)
    return sites, edges


def native_tables(archive, parent):
    # Align the two independently emitted streams by (event index, physical time).
    species_lines = archive.read("specnum_output.txt").decode().splitlines()
    count_lines = archive.read("procstat_output.txt").decode().splitlines()
    spec_header = (
        species_lines.pop(0)
        if species_lines[0].lstrip().startswith("Entry")
        else parent.read("specnum_output.txt").decode().splitlines()[0]
    ).split()[5:]
    step_header = (
        count_lines.pop(0)
        if count_lines[0].lstrip().startswith("Overall")
        else parent.read("procstat_output.txt").decode().splitlines()[0]
    ).split()[1:]
    species = {}
    for line in species_lines:
        _, n, clock, _, _, *counts = line.split()
        species[int(n), Decimal(clock)] = dict(zip(spec_header, map(int, counts), strict=True))
    processes = {}
    assert len(count_lines) % 3 == 0
    for marker, totals in zip(count_lines[::3], count_lines[2::3], strict=True):
        _, _, n, clock = marker.split()
        overall, *counts = map(int, totals.split())
        assert overall == sum(counts) == int(n)
        processes[int(n), Decimal(clock)] = dict(zip(step_header, counts, strict=True))
    assert species.keys() == processes.keys()
    return species, processes


def zacros_oracle(case):
    study = read(ZACROS / "zacros_validation.json")
    record = study["cases"][case]
    archive = ZACROS / record["archive"]
    v = output("zacros", case)
    q = read(ARCH / "zacros_qualification.json")[case]
    sha = digest(archive.read_bytes())
    assert sha == record["archive_sha256"] == v["provenance"]["native_output"]["sha256"]
    with ZipFile(archive) as z, ZipFile(ZACROS / study["cases"]["split"]["archive"]) as writer:
        for member, h in record["outputs_sha256"].items():
            assert digest(z.read(member)) == h
        if case == "resume":
            assert writer.read("restart.inf") == z.read("input-checkpoint.inf")
            assert digest(z.read("input-checkpoint.inf")) == study["checkpoint"]["restart_input_sha256"]
            assert digest(writer.read("lattice_input.dat")) == digest(z.read("lattice_input.dat"))
        rows, counters = native_tables(z, writer if case == "resume" else None)
        first, last = min(rows), max(rows)
        dt = last[1] - first[1]
        assert dt > 0
        steps = dict(
            re.findall(
                r"^step (\w+)\s+.*?^gas_reacs_prods H2 (-?\d+)$", z.read("mechanism_input.dat").decode(), re.M | re.S
            )
        )
        assert set(steps) == counters[first].keys()
        by_sign = {int(sign): counters[last][step] - counters[first][step] for step, sign in steps.items()}
        f, r = by_sign[-1], by_sign.get(1)
        assert f + (r or 0) == last[0] - first[0]
        measured = v["reaction_rates"][0]
        assert measured["forward"] == pytest.approx(float(f / dt), rel=1e-14)
        if r is None:
            assert measured["reverse"] == "not_applicable"
        else:
            assert measured["reverse"] == pytest.approx(float(r / dt), rel=1e-14)
        signed = f - (r or 0)
        assert measured["net"] == pytest.approx(float(signed / dt), rel=1e-14)
        mapping = {"HCu*": "H2-bridge", "HNi*": "H2-top", "H2": "H2-g"}
        initial, final = ({mapping[s]: n for s, n in rows[key].items()} for key in (first, last))
        changes = {s: final[s] - initial[s] for s in final}
        assert (
            initial == q["first_sample_counts"]
            and final == q["last_sample_counts"]
            and changes == q["net_species_changes"]
        )
        assert changes["H2-g"] == -signed
        for row in v["source_terms"]["species"]:
            assert row["net_production_rate"] == pytest.approx(float(changes[row["species_id"]] / dt), rel=1e-14)
        for row in v["source_terms"]["site_inventories"]:
            assert row["net_vacancy_rate"] == pytest.approx(float(-signed / dt), rel=1e-14)
        sites, edges = physical_edges((writer if case == "resume" else z).read("lattice_output.txt"))
        assert len(sites) == q["lattice_site_count"] == 18
        assert len(edges) == 18
        ni_sites = sum(kind == 1 for kind, _ in sites.values())
        assert ni_sites == 9 and q["lattice_site_count"] - ni_sites == 9
        for event in q["matching_multiplicity"]:
            assert event["matching_events"] == len(edges)
            assert event["patterns_per_reference_site"] == len(edges) / ni_sites == 2
        if case != "resume":
            sites_seeded = {}
            seeds = z.read("state_input.dat").decode() if "state_input.dat" in z.namelist() else ""
            for line in seeds.splitlines():
                if line.startswith("seed_on_sites"):
                    _, name, *ids = line.split()
                    for idx in ids:
                        sites_seeded[int(idx)] = (name, ids)
            empty = sum(i not in sites_seeded and j not in sites_seeded for i, j in edges)
            filled = sum(
                i in sites_seeded and j in sites_seeded and (case != "dent" or sites_seeded[i][1] == sites_seeded[j][1])
                for i, j in edges
            )
            assert empty + (filled if r is not None else 0) == q["initial_matches"]
        assert q["process_window"]["duration_s"] == pytest.approx(float(dt), rel=1e-14)
        assert q["steady_state"] is q["statistical_uncertainty"] is None
        assert (
            v["native_normalization"]["basis_kind"] == "simulation_cell"
            and v["native_normalization"]["denominator_value"] == 1
        )
        assert q["event_counts"] == {step: counters[last][step] - counters[first][step] for step in steps}
        return dict(
            archive_sha256=sha,
            first_event=first[0],
            last_event=last[0],
            start_s=str(first[1]),
            end_s=str(last[1]),
            duration_s=str(dt),
            forward_count=f,
            reverse_count=r,
            net_per_simulation_cell_s=float(signed / dt),
            first_species_counts=initial,
            last_species_counts=final,
            potential_matches_per_direction=len(edges),
            initial_matches=q["initial_matches"],
            steady_state=None,
            statistical_uncertainty=None,
        )


@pytest.mark.parametrize("case", ["phase2_5_2", "phase3_0"])
def test_catkinas_mat_against_analytical_oracle(case):
    catkinas_oracle(case)


@pytest.mark.parametrize("case", NATIVE_CASES)
def test_zacros_against_counter_and_lattice_oracle(case):
    zacros_oracle(case)


def test_restart_intervals_recover_continuous_trajectory_including_boundary():
    with (
        ZipFile(ZACROS / "benchmarks/continuous.zip") as continuous,
        ZipFile(ZACROS / "benchmarks/split.zip") as split,
        ZipFile(ZACROS / "benchmarks/resume.zip") as resume,
    ):
        for member in ("procstat_output.txt", "specnum_output.txt"):
            assert split.read(member) + resume.read(member) == continuous.read(member)
        _, a = native_tables(split, None)
        _, b = native_tables(resume, split)
        _, c = native_tables(continuous, None)
        end_a, start_b = max(a), min(b)
        assert end_a[0] == 7 and start_b[0] == 8 and not a.keys() & b.keys()
        boundary = {k: b[start_b][k] - a[end_a][k] for k in a[end_a]}
        assert boundary == {"r1_forward": 1, "r2_reverse": 0}
        assert max(c)[0] - min(c)[0] == (end_a[0] - min(a)[0]) + 1 + (max(b)[0] - start_b[0])
