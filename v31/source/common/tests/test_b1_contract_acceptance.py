"""Acceptance checks at the public V1/V2 boundary. Hand results and artifact hashes are independent."""

import copy
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pytest

from scripts.kinetic_data.stoichiometric_sources import build_matrices, conservation_residuals, generate_source_terms
from scripts.kinetic_parameters.rate_units import convert_coefficient
from scripts.multiphase_contracts import validate_bundle
from scripts.rate_output_v2 import convert_native_rate, validate_rate_output_v2
from test_native_rate_adapters import CASES, MATRIX, OUT, ROOT, cat, cat_inputs, kmc, kmc_network

FIX = ROOT / "tests/fixtures/multiphase"


def encoded(obj):
    return (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(obj):
    return digest(json.dumps(obj, separators=(",", ":"), sort_keys=True).encode())


def bound(ref):
    path, sep, member = ref["path"].partition("!/")
    if sep:
        with ZipFile(ROOT / path) as z:
            data = z.read(member)
    else:
        data = (ROOT / path).read_bytes()
    assert digest(data) == ref["sha256"], ref["path"]
    return data


def replay_lineage(engine, case):
    if engine == "catkinas":
        receipt, opts = cat_inputs(case)
        payload, q = cat.adapt(receipt, **opts)
        net_path = opts["network_path"]
        original = json.loads(receipt.read_bytes())
        run_id = original.get("run_id") or Path(original["closed_cycle"]["raw_local_directory"]).name
        if case == "phase3_0":
            parent = json.loads(bound(q["result_record"]))
            assert parent["format"] == "mkm-single-point-result/1" and parent["run_id"] == run_id
            assert parent["plan_sha256"] == original["raw_plan_sha256"]
            assert parent["output_hashes"] == original["output_hashes"]
            assert q["result_record"]["sha256"] == original["result_sha256"]
    else:
        receipt, net_path, run_id = MATRIX, kmc_network(case), case
        payload, q = kmc.adapt(receipt, case, net_path, root=ROOT)
        assert (
            json.loads(receipt.read_bytes())["cases"][case]["archive_sha256"]
            == payload["provenance"]["native_output"]["sha256"]
        )
    assert bound(q["receipt"]) == receipt.read_bytes()
    binding = payload["output_binding"]
    assert binding["run_id"] == run_id
    for ref in [*binding["native_inputs"], *payload["provenance"].values()]:
        bound(ref)
    parent_data = json.loads(bound(payload["provenance"]["dataset"]))
    network = json.loads(bound(payload["provenance"]["network"]))
    assert json.loads(net_path.read_bytes()) == network
    assert (
        canonical({k: v for k, v in network.items() if k != "network_version"})
        == payload["network_version"]
        == network["network_version"]
    )
    assert (
        canonical({k: v for k, v in parent_data.items() if k != "dataset_version"})
        == payload["dataset_version"]
        == parent_data["dataset_version"]
    )
    assert parent_data["network_version"] == network["network_version"]
    assert {r["reaction_id"]: r["parameter_set_id"] for r in payload["reaction_rates"]} == {
        r["reaction_id"]: r["parameter_set"]["parameter_set_id"] for r in parent_data["reactions"]
    }
    copy_without_id = copy.deepcopy(payload)
    claimed = copy_without_id["output_binding"].pop("dataset_id")
    assert claimed == "rates-" + canonical(copy_without_id)
    raw = encoded(payload)
    assert raw == (OUT / "replay" / f"{engine}-{case}.json").read_bytes()
    restored = json.loads(raw)
    assert restored == payload and restored["native_normalization"] == payload["native_normalization"]
    validate_rate_output_v2(restored, network=network)
    assert restored["validation"] == {"status": "unreviewed", "review": None}
    return dict(
        case=case,
        dataset_id=claimed,
        run_id=run_id,
        dataset_version=payload["dataset_version"],
        network_version=payload["network_version"],
        basis=payload["native_normalization"]["basis_kind"],
        inputs=binding["native_inputs"],
        provenance=payload["provenance"],
        parent_receipt=q["receipt"],
        output_sha256=digest(raw),
        qualification_sha256=digest(encoded(q)),
        schema=payload["schema_version"],
    ), q


def replay_all():
    result = {}
    for engine, cases in (("catkinas", ("phase2_5_2", "phase3_0")), ("zacros", CASES)):
        runs, qualifications = [], {}
        for case in cases:
            record, qualifications[case] = replay_lineage(engine, case)
            runs.append(record)
        combined = encoded(qualifications)
        assert combined == (OUT / f"{engine}_qualification.json").read_bytes()
        result[engine] = dict(runs=runs, qualification_file_sha256=digest(combined))
    assert len({r["dataset_id"] for group in result.values() for r in group["runs"]}) == 10
    return result


def test_ten_outputs_and_both_qualification_files_replay_byte_for_byte():
    assert replay_all() == replay_all()


def synthetic_rows(third):
    # D and I each contain H2 with charge +2. H carries +1. Z and Zs contain neutral O.
    def r(i, lhs, rhs, vacancies_in, vacancies_out, forward, reverse, net):
        return dict(
            reaction_id=f"r{i}",
            parameter_set_id=f"p{i}",
            reactants=lhs,
            products=rhs,
            sites_consumed=vacancies_in,
            sites_released=vacancies_out,
            forward=forward,
            reverse=reverse,
            net=net,
        )

    return [
        r(1, {"D": 1}, {"H": 2}, {"alpha": 2}, {}, 3, 1, 2),
        r(2, {"H": 2}, {"I": 1}, {"beta": 1}, {"alpha": 1}, 1, 2, -1),
        r(3, {"I": 1}, {"D": 1}, {}, {"alpha": 1, "beta": 1}, 2, 2 if third == 0 else None, third),
        r(4, {"Z": 1}, {"Zs": 1}, {"gamma": 1}, {}, 3, "not_applicable", 3),
    ]


@pytest.mark.parametrize("third", [0, None])
def test_three_phase_combination_against_hand_matrices(third):
    # Columns r1..r4. I is a single interfacial molecule on alpha and beta.
    species = ("D", "H", "I", "Z", "Zs")
    sites = ("alpha", "beta", "gamma")
    ns = np.array([[-1, 0, 1, 0], [2, -2, 0, 0], [0, 1, -1, 0], [0, 0, 0, -1], [0, 0, 0, 1]])
    nv = np.array([[-2, 1, 1, 0], [0, -1, 1, 0], [0, 0, 0, -1]])
    atom = np.array([[2, 1, 2, 0, 0], [0, 0, 0, 1, 1]])
    charge = np.array([2, 1, 2, 0, 0])
    footprint = np.array([[0, 1, 1, 0, 0], [0, 0, 1, 0, 0], [0, 0, 0, 0, 1]])
    assert not np.any(atom @ ns) and not np.any(charge @ ns) and not np.any(footprint @ ns + nv)
    nets = np.array([2, -1, 0, 3])
    assert (ns @ nets).tolist() == [-2, 6, -1, -3, 3] and (nv @ nets).tolist() == [-5, 1, -3]
    expected = [-2, 6, -1, -3, 3] if third == 0 else [None, 6, None, -3, 3]
    vacant = [-5, 1, -3] if third == 0 else [None, None, -3]
    rows = synthetic_rows(third)
    catalog = [
        dict(
            species_id=s,
            charge=int(charge[i]),
            composition={a: int(n) for a, n in zip(("H", "O"), atom[:, i]) if n},
            site_occupancy={q: int(n) for q, n in zip(sites, footprint[:, i]) if n},
        )
        for i, s in enumerate(species)
    ]
    for residual in conservation_residuals(build_matrices(rows), catalog).values():
        assert residual == {"elements": {"H": 0, "O": 0}, "charge": 0, "inventories": dict.fromkeys(sites, 0)}
    trial = json.loads((FIX / "rate_output_v2.json").read_bytes())
    trial["reaction_rates"] = rows
    trial["source_terms"] = {
        "species": [dict(species_id=s, net_production_rate=v) for s, v in zip(species, expected)],
        "site_inventories": [dict(site_id=s, net_vacancy_rate=v) for s, v in zip(sites, vacant)],
    }
    assert generate_source_terms(rows) == trial["source_terms"]
    validate_rate_output_v2(trial)


@pytest.mark.parametrize(
    ("kind", "unit", "missing"),
    [
        ("reference_site", "reference site", "sites_per_reference"),
        ("surface_area", "m²", "reference_mol_per_catalyst_m2"),
        ("catalyst_mass", "kg", "reference_mol_per_kg"),
        ("reactor_volume", "m³", "reference_mol_per_reactor_m3"),
    ],
)
def test_real_pair_remains_native_without_physical_mapping(kind, unit, missing):
    v = json.loads((OUT / "replay/catkinas-phase3_0.json").read_bytes())
    pair = v["native_normalization"]
    target = dict(pair, basis_kind=kind, reference_id=kind, denominator_unit=unit)
    if kind == "reference_site":
        target["inventory_ids"] = ["top-Ni"]
    else:
        del target["inventory_ids"]
    for role, value, numerator in (
        ("forward_flux", 94.00713283583823, "event"),
        ("reverse_flux", 12.494362674190553, "event"),
        ("net_progress", 81.5127701616477, "event"),
        ("species_source", 163.0255403232954, "molecule"),
        ("site_source", 0, "vacancy"),
    ):
        out = convert_native_rate(value, role, pair, target)
        assert out["value"] is None and out["missing"] == [missing]
        assert (
            out["native_value"] == value and out["native_basis"] == pair and out["native_numerator_unit"] == numerator
        )
    k = v["rate_coefficients"][0]["forward"]
    assert convert_coefficient(k["value"], k["unit"], "Pa^-1 s^-1", k["activity_orders"]) == pytest.approx(
        k["value"] / 100000
    )


def test_partial_kmc_population_evidence_cannot_become_directional_rate(tmp_path):
    # A synthetic copy retaining the real receipt-bound population series and terminal clock only.
    matrix = json.loads(MATRIX.read_bytes())
    record = matrix["cases"]["mono"]
    sample = tmp_path / "populations.zip"
    with ZipFile(MATRIX.parent / record["archive"]) as archive, ZipFile(sample, "w") as subset:
        for name in archive.namelist():
            if name != "procstat_output.txt":
                subset.writestr(name, archive.read(name))
    del record["outputs_sha256"]["procstat_output.txt"]
    record.update(archive=sample.name, archive_sha256=digest(sample.read_bytes()))
    manifest = tmp_path / "receipt.json"
    manifest.write_bytes(encoded(matrix))
    network = tmp_path / "network.json"
    network.write_bytes(kmc_network("mono").read_bytes())
    payload, q = kmc.adapt(manifest, "mono", network, root=tmp_path)
    validate_rate_output_v2(payload)
    assert q["net_species_changes"] == {"H2-g": -7, "H2-bridge": 7, "H2-top": 7}
    assert q["terminal_event_counter"] == 20 and q["terminal_physical_time_s"] > 0
    assert q["process_window"] is q["event_counts"] is None and q["missing_rate_evidence"]
    assert all(payload["reaction_rates"][0][k] is None for k in ("forward", "reverse", "net"))
    assert all(row["net_vacancy_rate"] is None for row in payload["source_terms"]["site_inventories"])
    assert all(row["net_production_rate"] is None for row in payload["source_terms"]["species"])


def test_shared_phase_catalogs_do_not_identify_a_shared_rate_observable():
    cat_output = json.loads((OUT / "replay/catkinas-phase3_0.json").read_bytes())
    cat_network = json.loads(bound(cat_output["provenance"]["network"]))
    cat_ads = next(row for row in cat_output["reaction_rates"] if row["reaction_id"] == "ads")
    phase_fields = {(s["surface_id"], s["phase_id"]) for s in cat_network["catalog"]["surfaces"]}
    assert phase_fields == {("facet-Ni", "fcc-Ni"), ("facet-Cu", "fcc-Cu")}
    for case in CASES:
        other = json.loads((OUT / f"replay/zacros-{case}.json").read_bytes())
        network = json.loads(bound(other["provenance"]["network"]))
        assert {(s["surface_id"], s["phase_id"]) for s in network["catalog"]["surfaces"]} == phase_fields
        assert cat_output["network_version"] != other["network_version"]
        assert len(cat_output["reaction_rates"]) == 4 and len(other["reaction_rates"]) == 1
        ads = other["reaction_rates"][0]
        assert cat_ads["reactants"] == ads["reactants"] and cat_ads["sites_consumed"] == ads["sites_consumed"]
        assert (cat_ads["products"] == ads["products"]) == (case != "dent")
        assert (ads["reverse"] == "not_applicable") == (case == "attractive")
        assert cat_output["conditions"]["temperature_K"] == other["conditions"]["temperature_K"] == 400
        assert cat_output["conditions"]["pressure_Pa"] == 160000 and other["conditions"]["pressure_Pa"] == 100000
        assert {r["species_id"] for r in other["source_terms"]["species"]}.isdisjoint({"HNO-g"})
        assert cat_output["native_normalization"]["basis_kind"] == "reference_site_pair"
        assert other["native_normalization"]["basis_kind"] == "simulation_cell"


def test_explicit_legacy_intake_and_version_isolation():
    historical = FIX / "valid.json"
    raw = historical.read_bytes()
    v1 = json.loads(raw)
    validate_bundle(v1)
    v2 = json.loads((OUT / "replay/zacros-mono.json").read_bytes())
    validate_rate_output_v2(v2)
    for validator, wrong in ((validate_rate_output_v2, v1), (validate_bundle, v2)):
        with pytest.raises(ValueError):
            validator(wrong)
    for version in (None, "2.2.0", "1.0.0"):
        bad = dict(v2, schema_version=version)
        if version is None:
            del bad["schema_version"]
        with pytest.raises(ValueError):
            validate_rate_output_v2(bad)
    with pytest.raises(ValueError):
        validate_rate_output_v2(dict(v2, unsupported_field="preserve me"))
    assert historical.read_bytes() == raw
