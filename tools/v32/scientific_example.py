"""Run the offline Fe evidence and analytical examples using independently installed role interpreters."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys


def sha(raw):
    return sha256(raw).hexdigest()


def fe_example():
    from sbq123.common.compat import historical_module
    api = historical_module("mkm", "scripts.reaction_network.builder")
    from scripts.runtime_resources import resource_path
    from scripts.scientific_intake import report
    from scripts.multiphase_contracts import read_artifact

    sources = {}
    def retained(name):
        path = resource_path("reports/multiphase/" + name)
        doc, digest = read_artifact(path)
        sources[name] = digest
        return doc

    mapping = retained("ch_co_registry_mapping_20261119.json")
    intake = retained("ch_co_intake_20261119.json")
    closure = retained("phase3_3_1/closure.json")
    eligibility = retained("phase3_2_2/eligibility.json")["fe110"]
    archived = retained("networks/network-" + eligibility["network"] + ".json")
    from scripts.reaction_network.catalog import check_network_version
    if (check_network_version(archived) != eligibility["network"]
            or intake["reaction_id"] not in archived["validation_report"]["levels"]):
        raise ValueError("Intake differs from archived Fe network")
    definition = api.from_registry_mapping(mapping, archived["project_id"])
    thermal = retained("phase2_2_chco_validation.json")
    records = [dict(role="definition", file="ch_co_registry_mapping_20261119.json",
                    sha256=sources["ch_co_registry_mapping_20261119.json"])]
    parent = api.build_network(definition, sources=records)
    for source in archived["source_artifacts"]:
        if sources.get(source["file"]) != source["sha256"]:
            raise ValueError("Archived Fe network source differs from the retained input")
    child = api.build_network(definition, intakes=[intake], thermochemistry=[thermal["calculation"]],
                              sources=archived["source_artifacts"])
    site_review = next(r["site_review"] for r in archived["reactions"] if r["definition"]["reaction_id"] == intake["reaction_id"])
    if child["network_version"] != site_review["proposal"]["parent_network_version"]:
        raise ValueError("Rebuilt intake network differs from the archived site review parent")
    with_sites = api.build_network(definition, intakes=[intake], thermochemistry=[thermal["calculation"]],
                                   sources=archived["source_artifacts"], site_proposal=site_review["proposal"],
                                   site_confirmation=site_review["confirmation"])
    if with_sites != archived:
        raise ValueError("Rebuilt site-review network differs from the original archive")
    state = report([intake], "kinetic_handoff")
    return dict(scope="Fe(110) archival electronic evidence; read-only reconstruction",
                reaction_id=intake["reaction_id"], registry_record=mapping["registry"], evidence=sources,
                project_id=archived["project_id"], archived_network_version=archived["network_version"],
                reproduced_site_review_version=with_sites["network_version"],
                parent_network_version=parent["network_version"], derived_network_version=child["network_version"],
                electronic_energies=child["reactions"][0]["definition"].get("electronic_energies"),
                intake_gaps=state["unresolved_fields"], validation=child["validation_report"],
                historical_four_reaction_closure={k: closure[k] for k in ("scope", "closed_for_nonzero_turnover",
                    "rate_qualified_reaction_count", "gate_blockers", "isolated_network_reason")},
                tof=None, drc=None, execution_authorized=False, promoted=False,
                badch="Unresolved per project brief; these source records supply no independent closure.")


def main():
    if sys.argv[1:] == ["--fe-worker"]:
        print(json.dumps(fe_example(), allow_nan=False))
        return
    cli = argparse.ArgumentParser(description=__doc__)
    for key in ("mkm-python", "kmc-python", "fixtures", "output"):
        cli.add_argument("--" + key, required=True, type=Path)
    cli.add_argument("--reactor-evidence", type=Path, help="Original trace-correction windows-originals directory")
    a = cli.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    exe = dict(mkm=a.mkm_python.resolve(), kmc=a.kmc_python.resolve())
    roots = {r: (a.fixtures / r).resolve() for r in exe}
    def save(name, value):
        (out / (name + ".json")).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf8")
        return value

    def run(role, *args, name):
        call = [exe[role], "-I", "-B", *args]
        env = dict(os.environ, SBQ123_ROLE_DATA=str(roots[role]), SBQ123_MKM_PYTHON=str(exe["mkm"]))
        data = subprocess.check_output(call, cwd=out, env=env)
        return save(name, json.loads(data))

    def analysis(role, *args, name):
        return run(role, "-m", "sbq123.analysis", *args, name=name)

    fe = run("mkm", Path(__file__).resolve(), "--fe-worker", name="fe-archived-intake")
    base = Path("reports/multiphase/stage_b1_4/replay")
    for role, file in [("mkm", "catkinas-phase3_0"), ("kmc", "zacros-mono")]:
        source = roots[role] / base / (file + ".json")
        analysis(role, "rates", role, source, sha(source.read_bytes()), name=role + "-rates")
    mkm = roots["mkm"]
    source = mkm / base / "catkinas-phase3_0.json"
    study = analysis("mkm", "study", mkm, name="derivatives")
    plan = analysis("mkm", "follow-up", mkm, source, sha(source.read_bytes()), out / "proposals", name="planning")
    run_path = mkm / "reports/workflow_development/stage_v2_4_4_step3/nicu-400k-001"
    binding = "7568c7f5076b392026735ed835e7f4322c8bbaea64d4b66cddcb17116be33d54"
    point = analysis("mkm", "point", run_path, binding, name="mkm-point")
    window_dir = Path("reports/workflow_development/stage_v3_1_step2_kmc_window_bridge/synthetic-example")
    report = window_dir / "exchange-integration.json"
    window = analysis("kmc", "retained-window", report.as_posix(), sha((roots["kmc"] / report).read_bytes()), name="mock-window")
    manifest = roots["kmc"] / window_dir / "manifest-0.25-5.25.json"
    queries = [dict(kind="coverage", inventory="bridge-Cu", species="H2-bridge"),
               dict(kind="reaction_rate", reaction="ads", direction="forward"), dict(kind="site_utilization", inventory="bridge-Cu"),
               dict(kind="molecular_population", species="H2-bridge"),
               dict(kind="tof", overall_stoichiometry={"H2-g": -1, "NO-g": -2, "HNO-g": 2}),
               dict(kind="selectivity", products=["HNO-g"], species="HNO-g")]
    save("comparison-request", dict(format="mkm-kmc-comparison/1", observables=queries,
         mkm=dict(run=str(run_path), binding_sha256=binding), kmc=dict(path=str(manifest), sha256=sha(manifest.read_bytes()))))
    req = out / "comparison-request.json"
    optional = []
    if a.reactor_evidence:
        owner_pins = {"PFR": "3c060b5a819b662d453c87f63e27071666e136566647bb4b5390e92fa394b23e",
                      "CSTR": "eb324009a2edc50fb8b60da16f4312e996c687342c8354e6c03fb4a62bb12a81"}
        for kind, pin in owner_pins.items():
            f = (a.reactor_evidence / f"replacement-{kind}-1e-16-stdout.json").resolve()
            raw = f.read_bytes()
            if sha(raw) != pin:
                raise ValueError("Different archived Reactor calculation")
            digest = json.loads(raw)["result_sha256"]
            analysis("mkm", "reactor", f, digest, name=kind)
            optional = ["--reactor", f, "--reactor-sha256", digest]
    compared = analysis("kmc", "comparison", mkm, req, sha(req.read_bytes()), *optional, name="comparison")
    save("summary", dict(fe_reaction=fe["reaction_id"], fe_tof=fe["tof"], point_tof=point["analysis"]["tof"]["overall"],
         mass=point["analysis"]["mass_normalization"], sensitivity_count=len(study["direct_observations"]),
         proposals=[p["calculation"] for p in plan["proposals"]], window=window["statistics"],
         comparison=[row["compatibility"] for row in compared["comparison"]["comparisons"]], execution_authorized=False))


if __name__ == "__main__":
    main()
