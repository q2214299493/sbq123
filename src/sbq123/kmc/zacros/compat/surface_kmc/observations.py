"""Read Zacros 4.0 site snapshots and independently clocked cumulative output streams."""

import math
import os
import re
from collections import Counter, defaultdict

from scripts.native_inputs import integer
from scripts.scientific_validation import finite_number
from scripts.surface_kmc.native import event_leg_orders
from scripts.surface_kmc.trajectory_statistics import process_samples, species_samples


from sbq123.common.evidence.registry import entry

ENGINE = entry("engine_families","zacros")["archived_engine_sha256"]
STREAMS = ("general_output.txt", "specnum_output.txt", "procstat_output.txt")


def _output(path, limit):
    with path.open("rb") as stream:
        if os.fstat(stream.fileno()).st_size > limit:
            raise ValueError(f"Output exceeds collection budget: {path.name}")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"Output exceeds collection budget: {path.name}")
    return data


def _spatial_boundary(receipt, interval):
    """The last due global frame must agree with the writer's validated event-one species stream."""
    last = integer(receipt.get("last_snapshot_step"), "writer last_snapshot_step", 0)
    sampled = receipt["tail"]["specnum"][0]
    if last != sampled - sampled % interval or not receipt.get("history_header"):
        raise ValueError("Spatial checkpoint disagrees with the writer's sampling horizon")
    if receipt["terminal_time_s"] is None:
        raise ValueError("Spatial checkpoint has no finite terminal clock")
    return dict(last_snapshot_step=last, terminal_time_s=receipt["terminal_time_s"])


def check_lattice_output(raw, walk):
    """4.0 writes index-zero vectors, both zero for an explicit lattice, and pads neighbor lists."""
    nodes = {n["index"]: n for n in walk["nodes"]}
    adjacent = {i: set() for i in nodes}
    for i, j, _ in walk["edges"]:
        adjacent[i].add(j)
        adjacent[j].add(i)
    seen = set()
    vectors = []
    for line in raw.decode("ascii").splitlines():
        if not line.strip():
            continue
        index, x, y, typ, degree, *links = line.split()
        i = int(index)
        if i == 0:
            if any(map(int, (typ, degree, *links))):
                raise ValueError("Invalid native lattice vector metadata")
            vectors.append([float(x), float(y)])
            continue
        if i not in nodes or i in seen:
            raise ValueError("Unknown or repeated lattice output node")
        node = nodes[i]
        degree = int(degree)
        bonds = list(map(int, links))
        if (
            int(typ) != node["type_index"]
            or degree != len(adjacent[i])
            or set(bonds[:degree]) != adjacent[i]
            or any(bonds[degree:])
            or not all(
                math.isclose(float(a), b, rel_tol=1e-10, abs_tol=1e-10)
                for a, b in zip((x, y), node["xy_angstrom"], strict=True)
            )
        ):
            raise ValueError("Native lattice coordinate, inventory or neighbor mismatch")
        seen.add(i)
    expected = walk["cell_vectors_A"]
    if vectors and not expected:
        expected = [[0.0, 0.0], [0.0, 0.0]]
    if len(vectors) != len(expected) or any(
        not math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-10)
        for left, right in zip(vectors, expected, strict=True)
        for a, b in zip(left, right, strict=True)
    ):
        raise ValueError("Native lattice cell vectors differ")
    if seen != nodes.keys():
        raise ValueError("Incomplete lattice output")


def _frame_state(rows, inventory, surface, neighbors, footprints, orders):
    sites, groups = {}, defaultdict(dict)
    for _ in inventory:
        row = next(rows, "").split()
        if len(row) != 4:
            raise ValueError("Truncated or malformed history frame")
        i, entity, code, leg = map(int, row)
        if i not in inventory or i in sites or not 0 <= code <= len(surface) or entity <= 0 or leg <= 0:
            raise ValueError("Invalid snapshot assignment")
        sid = surface[code - 1] if code else None
        sites[i] = sid
        if leg in groups[entity]:
            raise ValueError("Duplicate native dentate leg")
        groups[entity][leg] = i
    molecules, occupied = Counter(), Counter()
    for legs in groups.values():
        ordered = [legs[k] for k in sorted(legs)]
        sid = sites[ordered[0]]
        if (
            set(legs) != set(range(1, len(legs) + 1))
            or any(sites[i] != sid for i in ordered)
            or sid is None
            and len(legs) != 1
        ):
            raise ValueError("Inconsistent molecular entity")
        if sid:
            labels = tuple(inventory[i] for i in ordered)
            if Counter(labels) != footprints[sid] or orders[sid] and labels not in orders[sid]:
                raise ValueError("Snapshot molecule footprint or dentate order differs")
            seen = {ordered[0]}
            for _ in ordered:
                seen.update(i for i in ordered if neighbors[i] & seen)
            if len(seen) != len(ordered):
                raise ValueError("Disconnected snapshot entity")
            occupied.update(labels)
            molecules[sid] += 1
    return sites, groups, molecules, occupied


def history_frames(raw, walk, mapping, dataset, events):
    """Yield checked native configurations. Position in a molecule is its ordered dentate leg."""
    rows = iter(raw.decode("ascii").splitlines())
    header = {}
    for line in rows:
        if line.startswith("configuration"):
            break
        if ":" in line:
            tag, value = line.split(":", 1)
            header[tag] = value.split()
    else:
        raise ValueError("Missing history configuration")
    surface = sorted(mapping["surface_indices"], key=mapping["surface_indices"].get)
    if header.get("Surface_Species") != [mapping["species_names"][k] for k in surface]:
        raise ValueError("History species ordering differs")
    gas = sorted(mapping["gas_indices"], key=mapping["gas_indices"].get) if "Gas_Species" in header else []
    if "Gas_Species" in header and header["Gas_Species"] != [mapping["species_names"][k] for k in gas]:
        raise ValueError("History gas species ordering differs")
    nodes = walk["nodes"]
    inventory = {n["index"]: n["inventory_id"] for n in nodes}
    neighbors = {i: set() for i in inventory}
    for i, j, _ in walk["edges"]:
        neighbors[i].add(j)
        neighbors[j].add(i)
    footprints = {s["species_id"]: s["site_occupancy"] for s in dataset["species"]}
    orders = event_leg_orders(events)
    previous = None
    while line is not None:
        cfg = line.split()
        if len(cfg) != 6 or cfg[0] != "configuration":
            raise ValueError("Malformed history configuration")
        step = integer(int(cfg[2]), "snapshot step", 0)
        time = finite_number(cfg[3], "snapshot time", nonnegative=True)
        finite_number(cfg[5], "snapshot energy")
        if float(cfg[4]) != dataset["reactions"][0]["parameter_set"]["temperature_K"]:
            raise ValueError("Snapshot temperature differs")
        if previous and (step <= previous[0] or time < previous[1]):
            raise ValueError("Nonmonotone history")
        previous = step, time
        sites, groups, molecules, occupied = _frame_state(
            rows, inventory, surface, neighbors, footprints, orders
        )
        gas_counts = {}
        if gas:
            counts = next(rows, "").split()
            if len(counts) != len(gas):
                raise ValueError("Missing or malformed history gas counts")
            gas_counts = dict(zip(gas, map(int, counts), strict=True))
        pairs = Counter(
            (contact, *sorted((sites[i] or "*", sites[j] or "*"))) for i, j, contact in walk["edges"]
        )
        yield dict(
            step=step,
            time_s=time,
            sites=sites,
            molecules=dict(molecules),
            entities={eid: dict(legs) for eid, legs in groups.items() if sites[next(iter(legs.values()))]},
            gas_counts=gas_counts,
            occupied=dict(occupied),
            coverage={k: occupied[k] / v for k, v in walk["capacities"].items()},
            neighbor_pairs=[dict(interface_id=c, species=[a, b], count=v) for (c, a, b), v in pairs.items()],
        )
        line = next((s for s in rows if s.strip()), None)


def _collect_history(dest, plan, config, dataset, mapping, events, result, outputs, receipt):
    limit = plan["max_output_bytes_per_file"]
    history = "history_output.txt"
    parent = plan["lineage"]
    interval = config["zacros"]["snapshot_every_events"]
    last = parent["last_snapshot_step"] if parent else None
    header = parent["history_header"].encode("ascii") if parent else b""
    path = dest / history
    body = b""
    if path.exists():
        outputs[history] = body = _output(path, limit)
    prefix, sep, frames = body.partition(b"configuration")
    if prefix.strip():
        if parent and prefix.split() != header.split():
            raise ValueError("History header differs from checkpoint writer")
        header = prefix
    receipt["history_header"] = header.decode("ascii")
    pop = {n: (t, v) for n, t, v in result["specnum"]}
    expected = 0 if last is None else last + interval
    first = None
    snapshots = (
        history_frames(header + sep + frames, mapping["topology"], mapping, dataset, events) if sep else ()
    )
    for frame in snapshots:
        # Zacros configuration ordinal may reset. The event field must identify a verified global sample.
        n = frame["step"]
        if n != expected:
            raise ValueError(f"Expected global snapshot step {expected}, received {n}")
        if n not in pop:
            raise ValueError("Snapshot has no matching global event sample")
        if first is None:
            first = n
        if n == 0 and not plan["lineage"]:
            observed = {
                (frame["sites"][legs[1]], tuple(legs[k] for k in sorted(legs)))
                for legs in frame["entities"].values()
            }
            if observed != {(sid, tuple(indices)) for sid, indices in config["zacros"]["seeds"]}:
                raise ValueError("Initial snapshot differs from ordered seed locations")
        time, values = pop[n]
        if any(values[s] != count for s, count in frame["gas_counts"].items()):
            raise ValueError("Spatial snapshot contradicts gas counts")
        if time != frame["time_s"] or any(
            frame["molecules"].get(s, 0) != values[s] for s in mapping["surface_indices"]
        ):
            raise ValueError("Spatial snapshot contradicts species or event clock")
        last = n
        expected += interval
    if expected <= result["specnum"][-1][0]:
        raise ValueError(f"Missing scheduled snapshot at global step {expected}")
    receipt.update(first_snapshot_step=first, last_snapshot_step=last)


def join_samples(writer, continuation):
    """Join cumulative rows at a checkpoint. Native event-one streams may omit the terminal row."""
    if not writer or not continuation:
        raise ValueError("Empty restart stream")
    last, first = writer[-1], continuation[0]
    if first[0] == last[0]:
        if first != last:
            raise ValueError("Contradictory checkpoint boundary")
        return writer + continuation[1:]
    if first[0] != last[0] + 1 or first[1] < last[1]:
        raise ValueError("Gap or reversal across checkpoint")
    return writer + continuation


def _terminal(general, mapping, max_steps, parent):
    restart_time = None
    if "> Normal termination <" not in general or re.search(r"(?im)^\s*(?:fatal|error code)", general):
        raise ValueError("Native reader or termination failure")
    if parent:
        marker = re.search(r"restart No \d+ from KMC step (\d+) and t = (\S+)", general, re.I)
        if (
            not marker
            or int(marker[1]) != parent["terminal_step"]
            or "Restart information successfully read" not in general
        ):
            raise ValueError("Checkpoint reader lineage differs")
        restart_time = finite_number(marker[2], "restart time", nonnegative=True)
        if "terminal_time_s" in parent and (
            parent["terminal_time_s"] is None
            or not math.isclose(restart_time, parent["terminal_time_s"], rel_tol=1e-6)
        ):
            raise ValueError("Restart clock differs from the writer's terminal clock")
    else:
        readers = ["simulation", "lattice", "energetics", "mechanism"]
        if mapping["initial_state"] == "seeded":
            readers.append("initial state")
        if not re.search(r"\bZACROS 4\.0\b", general, re.I) or any(
            f"Finished reading {r} input." not in general for r in readers
        ):
            raise ValueError("Incomplete Zacros 4.0 input reader evidence")
        count = re.search(r"Total number of lattice sites:\s*(\d+)", general)
        if not count or int(count[1]) != mapping["site_count"]:
            raise ValueError("Native lattice capacity differs")
    terminal = re.search(r"Events occurred:\s*(\d+)", general)
    clock = re.search(r"Current KMC time:\s*(\S+)", general)
    if not terminal or not clock or int(terminal[1]) > max_steps:
        raise ValueError("Missing terminal counters or step budget exceeded")
    end = int(terminal[1])
    time = finite_number(clock[1], "terminal time", nonnegative=True)
    sentinel = time >= 1e300
    if sentinel and "801002" not in general:
        raise ValueError("Unexplained terminal clock sentinel")
    return end, time, sentinel, restart_time


def read_trajectory(outputs, dataset, mapping, events, *, max_steps, parent=None):
    general = outputs["general_output.txt"].decode("ascii")
    end, time, sentinel, restart_time = _terminal(general, mapping, max_steps, parent)
    headers = dict(parent["headers"]) if parent else {}
    samples = {}
    names = {v: k for k, v in mapping["species_names"].items()}
    t = dataset["reactions"][0]["parameter_set"]["temperature_K"]
    for name in ("procstat", "specnum"):
        raw = outputs[name + "_output.txt"]
        labels = headers.get(name)
        series = (
            process_samples(raw, labels) if name == "procstat" else species_samples(raw, names, t, labels)
        )
        if not labels:
            headers[name] = raw.decode("ascii").splitlines()[0].split()
        start = parent["terminal_step"] if parent else 0
        if (
            not series
            or series[0][0] != start
            or series[-1][0] not in (end - 1, end)
            or any(b[0] != a[0] + 1 for a, b in zip(series, series[1:]))
            or series[-1][1] > time
            and not math.isclose(series[-1][1], time, rel_tol=1e-6)
        ):
            raise ValueError("Incomplete event-one stream or inconsistent terminal clock")
        if parent and not math.isclose(series[0][1], restart_time, rel_tol=1e-12):
            raise ValueError("Continuation clock differs from checkpoint")
        samples[name] = series
    proc, pop = samples["procstat"], samples["specnum"]
    if parent and "tail" in parent:
        proc = join_samples([tuple(parent["tail"]["procstat"])], proc)
        pop = join_samples([tuple(parent["tail"]["specnum"])], pop)
        if any(b[2][k] < v for a, b in zip(proc, proc[1:]) for k, v in a[2].items()):
            raise ValueError("Native process counter decreased across checkpoint")
    _check_populations(proc, pop, mapping, dataset, events)
    return dict(
        terminal_step=end,
        terminal_time_s=None if sentinel else time,
        absorbing=sentinel,
        warnings=sorted(set(re.findall(r"Warning code (\d+)", general))),
        headers=headers,
        **samples,
    )


def _check_populations(proc, pop, mapping, dataset, events):
    steps = {x["native_step"]: e for x, e in zip(mapping["event_checks"], events, strict=True)}
    if set(proc[0][2]) != steps.keys():
        raise ValueError("Unknown native process columns")
    proc_by_step = {n: (tm, counts) for n, tm, counts in proc}
    previous = None
    surface = mapping["surface_indices"]
    capacities = mapping.get("topology", {}).get("capacities")
    footprints = {
        s["species_id"]: s["site_occupancy"] for s in dataset["species"] if s["species_id"] in surface
    }
    for n, tm, values in pop:
        if any(values[s] < 0 for s in surface):
            raise ValueError("Negative surface population")
        used = Counter()
        for sid, foot in footprints.items():
            for k, v in foot.items():
                used[k] += values[sid] * v
        if (
            sum(used.values()) > mapping["site_count"]
            or capacities
            and any(v > capacities[k] for k, v in used.items())
        ):
            raise ValueError("Impossible surface inventory")
        if n in proc_by_step:
            pt, counters = proc_by_step[n]
            if tm != pt:
                raise ValueError("Native sample clocks disagree")
            if previous:
                old, old_counts = previous
                delta = Counter()
                for step, e in steps.items():
                    count = counters[step] - old_counts[step]
                    for sid in values:
                        r = e["reaction"]
                        delta[sid] += count * (r["products"].get(sid, 0) - r["reactants"].get(sid, 0))
                if any(values[s] - old[s] != delta[s] for s in values):
                    raise ValueError("Population change differs from event stoichiometry")
            previous = values, counters
