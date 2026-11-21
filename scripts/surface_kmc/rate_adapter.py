"""Project receipt-bound Zacros process statistics on one whole simulated lattice."""
import argparse
import json
import math
import re
from pathlib import Path
from zipfile import Path as Member
from zipfile import ZipFile

from scripts.artifact_io import sha256_bytes
from scripts.kinetic_data.native_rate_output import artifact, build_output, conditions_pa, require
from scripts.kinetic_data.stoichiometric_sources import generate_source_terms
from scripts.multiphase_contracts import read_unique_json
from scripts.native_model import assemble, with_checkpoint
from scripts.surface_kmc.trajectory_statistics import process_samples, sampling_window, species_samples


def _member(z, name, archive, expected=None):
    raw = z.read(name)
    digest = sha256_bytes(raw)
    require(expected is None or digest == expected, f"SHA-256 differs for archive member {name}")
    return {"path": archive["path"] + "!/" + name, "sha256": digest}


def _header_sources(folder, study, case, checkpoint_hash):
    lineage = study.get("checkpoint", {})
    require(lineage.get("reader_case") == case and lineage["restart_input_sha256"] == checkpoint_hash,
            "Missing checkpoint lineage for continuation")
    writer = study["cases"][lineage["writer_case"]]
    archive = folder / writer["archive"]
    require(sha256_bytes(archive.read_bytes()) == writer["archive_sha256"], "Writer archive SHA-256 differs")
    with ZipFile(archive) as z:
        require(sha256_bytes(z.read("restart.inf")) == checkpoint_hash, "Checkpoint differs from writer")
        headers = {}
        for name in ("procstat_output.txt", "specnum_output.txt"):
            raw = z.read(name)
            require(sha256_bytes(raw) == writer["outputs_sha256"][name], "Writer output SHA-256 differs")
            headers[name] = raw.decode("ascii").splitlines()[0].split()
    return headers, dict(lineage, writer_archive_sha256=writer["archive_sha256"])


def _observations(dataset, events, counts, duration):
    steps = {}
    for e in events:
        direction = e["native_step"].rsplit("_", 1)[-1]
        key = e["reaction_id"], direction
        require(direction in ("forward", "reverse") and key not in steps, "Ambiguous native step assignment")
        steps[key] = e["native_step"]
    if counts is not None:
        require(set(steps.values()) == set(counts), "Process counters differ from native mechanism steps")
    progress, deltas = {}, []
    for model in dataset["reactions"]:
        rid = model["reaction_id"]
        status = model["direction"]["status"]
        require(status in ("reversible", "irreversible"), f"Unknown direction model for {rid}")
        reversible = status == "reversible"
        values = {}
        for direction in ("forward", "reverse") if reversible else ("forward",):
            step = steps[rid, direction]
            values[direction] = counts[step] if counts is not None else None
        f, r = values["forward"], values.get("reverse", 0)
        net = None if counts is None else f - r
        deltas.append(dict(reaction_id=rid, **model["direction"]["forward"], net=net))
        progress[rid] = {k: v / duration if duration and v is not None else None for k, v in dict(values, net=net).items()}
        if not reversible:
            progress[rid]["reverse"] = "not_applicable"
    return progress, deltas


def _read_samples(z, outputs, headers, manifest, dataset, record):
    mapping = manifest["validation"]
    processes, populations = [], []
    proc, spec = "procstat_output.txt", "specnum_output.txt"
    temperature = dataset["reactions"][0]["parameter_set"]["temperature_K"]
    if proc in outputs:
        processes = process_samples(z.read(proc), headers.get(proc))
    if spec in outputs:
        names = {v: k for k, v in mapping["species_names"].items()}
        populations = species_samples(z.read(spec), names, temperature, headers.get(spec))
    process_clock = {n: t for n, t, _ in processes}
    require(all(process_clock.get(n, t) == t for n, t, _ in populations), "Species and process clocks disagree")
    window, counts = sampling_window(processes)
    pop_window, changes = sampling_window(populations)
    duration = window["duration_s"] if window else None
    events = mapping["event_checks"]
    progress, delta_rows = _observations(dataset, events, counts, duration)
    if counts is not None and pop_window is not None and window == pop_window:
        projected = generate_source_terms(delta_rows)["species"]
        expected = {r["species_id"]: r["net_production_rate"] for r in projected}
        require(all(expected.get(s, 0) == n for s, n in changes.items()), "Native species changes differ from process counts")
    if populations:
        species_order = [sid for sid, _ in sorted(mapping["surface_indices"].items(), key=lambda item: item[1])]
        species_order += [sid for sid, _ in sorted(mapping["gas_indices"].items(), key=lambda item: item[1])]
        for sample, field in ((populations[0], "first_record_species_counts"), (populations[-1], "last_sample_species_counts")):
            if field not in record:
                continue
            require([sample[2][sid] for sid in species_order] == record[field], f"Species counts differ from {field}")
        require(pop_window["first_event"] == record.get("first_record_event", pop_window["first_event"])
                and pop_window["last_event"] == record.get("last_sample_event", pop_window["last_event"]),
                "Species window differs from receipt")
    diagnostics = dict(process_window=window, event_counts=counts, population_window=pop_window,
                       first_sample_counts=populations[0][2] if populations else None,
                       last_sample_counts=populations[-1][2] if populations else None, net_species_changes=changes,
                       rate_qualification="observed finite-window mean" if duration else "unavailable",
                       missing_rate_evidence=None if duration else "Two labeled process samples separated by positive physical time are required.")
    return progress, diagnostics


def adapt(receipt_path, case, network_path, *, root):
    receipt_path = Path(receipt_path)
    study = read_unique_json(receipt_path)
    record = study["cases"][case]
    path = receipt_path.parent / record["archive"]
    archive = artifact(path, root, record["archive_sha256"])
    network = read_unique_json(Path(network_path))
    with ZipFile(path) as z:
        require(len(z.namelist()) == len(set(z.namelist())), "Duplicate native archive member")
        dataset, config, manifest = [read_unique_json(Member(z, name)) for name in ("dataset.json", "configuration.json", "manifest.json")]
        manifest_ref = _member(z, "manifest.json", archive, record["input_manifest_sha256"])
        files, regenerated = assemble("zacros", dataset, config)
        headers, lineage = {}, None
        if "restart_receipt" in manifest:
            checkpoint = z.read("input-checkpoint.inf")
            _, regenerated = with_checkpoint(files, regenerated, checkpoint, manifest["restart_receipt"])
            headers, lineage = _header_sources(receipt_path.parent, study, case, sha256_bytes(checkpoint))
            require(manifest["restart_receipt"]["model_sha256"] == lineage["restart_model_sha256"], "Restart model lineage differs")
        require(regenerated == manifest, "Archived native input manifest differs from bound model")
        inputs = [_member(z, "input-checkpoint.inf" if name == "restart.inf" else name, archive, digest)
                  for name, digest in sorted(manifest["files"].items())]
        outputs = {name: _member(z, name, archive, h) for name, h in sorted(record["outputs_sha256"].items())}
        general = z.read("general_output.txt").decode("ascii")
        require("general_output.txt" in outputs and "> Normal termination <" in general and record["exit_code"] == 0,
                "Missing receipt-bound native termination")
        mapping = manifest["validation"]
        observed = re.search(r"Events occurred:\s*(\d+)", general)
        total_events = int(observed[1]) if observed else record.get("native_events_reported")
        if record.get("native_events_reported") is not None:
            require(total_events == record["native_events_reported"], "Native event count differs from receipt")
        terminal = re.search(r"Current KMC time:\s*(\S+)", general)
        terminal_time = float(terminal[1]) if terminal else None
        sentinel = "801002" in record["native_warning_codes"] and terminal_time is not None and terminal_time >= 1e300
        require(terminal_time is None or math.isfinite(terminal_time) and terminal_time >= 0, "Invalid native physical time")
        if lineage is not None:
            restart_step = re.search(r"restart No \d+ from KMC step (\d+)", general, re.I)
            require(restart_step and int(restart_step[1]) == lineage["resume_start_step"] and total_events == lineage["resume_end_step"],
                    "Continuation counters differ from checkpoint receipt")
        parameters = dataset["reactions"][0]["parameter_set"]
        sim = dict((p[0], p[1:]) for line in z.read("simulation_input.dat").decode().splitlines() if (p := line.split()))
        seed = int(sim["random_seed"][0]) if "random_seed" in sim else None
        version = study["engine"].split(maxsplit=1)
        require(len(version) == 2 and version[0].lower() == "zacros", "Missing engine version")
        if lineage is None:
            require(re.search(r"\bZacros\s+" + re.escape(version[1]) + r"\b", general, re.I)
                    and int(re.search(r"Total number of lattice sites:\s*(\d+)", general)[1]) == mapping["site_count"],
                    "Native version or lattice size differs")
        require(("seed" not in study or seed == study["seed"]) and float(sim["temperature"][0]) == study["temperature_K"] == parameters["temperature_K"],
                "Native seed or temperature differs from the receipt")
        obs, diagnostics = _read_samples(z, outputs, headers, manifest, dataset, record)
        lattice = _member(z, "lattice_input.dat", archive, manifest["files"]["lattice_input.dat"])
        basis = dict(basis_kind="simulation_cell", reference_id="lattice-" + lattice["sha256"], denominator_unit="simulation cell",
                     definition="One complete simulated periodic lattice, including all repeated primitive cells.")
        if diagnostics["process_window"] and total_events is not None:
            require(diagnostics["process_window"]["last_event"] <= total_events, "Process window exceeds terminal event count")
        payload = build_output(dataset, network, engine=dict(name="Zacros", version=version[1]), run_id=case,
                               conditions=conditions_pa(study["temperature_K"], float(sim["pressure"][0]), mapping["partial_pressure_bar"]),
                               basis=basis, inputs=inputs, observations=obs,
                               provenance=dict(network=artifact(network_path, root), dataset=_member(z, "dataset.json", archive),
                                               native_output=archive))
        diagnostics.update(receipt=artifact(receipt_path, root), manifest=manifest_ref, native_outputs=outputs, seed=seed,
                           lattice=lattice, lattice_site_count=mapping["site_count"], repeat_cell=config["zacros"]["repeat_cell"],
                           matching_multiplicity=mapping["event_checks"], initial_matches=record["native_initial_matches"],
                           executable_sha256=study["executable_sha256"],
                           population_convention="Surface columns count molecules; gas columns count cumulative exchange.",
                           event_definitions={r["reaction_id"]: r["model"]["local_event"] for r in dataset["reactions"]},
                           terminal_event_counter=total_events, terminal_physical_time_s=None if sentinel else terminal_time,
                           absorbing_clock_sentinel=sentinel, checkpoint=lineage, native_warning_codes=record["native_warning_codes"],
                           termination="normal", steady_state=None, statistical_uncertainty=None,
                           statistical_limitation="Single short trajectory. No reviewed stationary window or independent replicate ensemble.")
    return payload, diagnostics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("case")
    parser.add_argument("network", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--qualification", action="store_true")
    args = parser.parse_args()
    print(json.dumps(adapt(args.receipt, args.case, args.network, root=args.root)[int(args.qualification)], indent=2, allow_nan=False))
