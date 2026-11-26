"""Finite-window spatial KMC observations and independent-seed precision estimates."""

from collections import Counter
from math import sqrt
from statistics import mean, stdev

from scripts.artifact_io import sha256_json
from scripts.native_inputs import integer
from scripts.scientific_validation import finite_number


def window_analysis(trajectory, dataset, mapping, start_s, end_s, *, denominator=1, basis="simulation_cell"):
    """Integrate event-one populations as left-held states; subtract cumulative counters on their own clock."""
    start = finite_number(start_s, "observation start", nonnegative=True)
    end = finite_number(end_s, "observation end", positive=True)
    scale = finite_number(denominator, "rate denominator", positive=True)
    if end <= start or not basis or (basis == "simulation_cell" and scale != 1):
        raise ValueError("Invalid observation window or normalization")
    proc, pop = trajectory["procstat"], trajectory["specnum"]
    for series in (proc, pop):
        if not series or series[0][1] > start or series[-1][1] < end or end >= 1e300:
            raise ValueError("Observation window exceeds finite sampled evidence")
    duration = end - start
    molecule_time = Counter()
    for (_, left, values), (_, right, _) in zip(pop, pop[1:]):
        dt = min(right, end) - max(left, start)
        if dt > 0:
            for s in mapping["surface_indices"]:
                molecule_time[s] += dt * values[s]
    capacities = mapping["topology"]["capacities"]
    inventory = {k: Counter() for k in capacities}
    for species in dataset["species"]:
        sid = species["species_id"]
        for k, legs in (species.get("site_occupancy") or {}).items():
            inventory[k][sid] = molecule_time[sid] * legs / (duration * capacities[k])
    first, last = (next(row[2] for row in reversed(proc) if row[1] <= t) for t in (start, end))
    counts = {k: last[k] - v for k, v in first.items()}
    frequency = {k: v / duration for k, v in counts.items()}
    pathways = {}
    production = Counter()
    steps = {
        (e["reaction_id"], e["native_step"].rsplit("_", 1)[1]): e["native_step"]
        for e in mapping["event_checks"]
    }
    for row in dataset["reactions"]:
        rid = row["reaction_id"]
        forward = counts[steps[rid, "forward"]]
        reverse = counts[steps[rid, "reverse"]] if row["direction"]["status"] == "reversible" else 0
        net = (forward - reverse) / (duration * scale)
        pathways[rid] = dict(forward=forward, reverse=reverse, net_rate=net)
        reaction = row["direction"]["forward"]
        for sid in reaction["products"].keys() | reaction["reactants"].keys():
            production[sid] += net * (reaction["products"].get(sid, 0) - reaction["reactants"].get(sid, 0))
    return dict(
        window_s=[start, end],
        denominator=scale,
        basis=basis,
        event_frequency_s_inverse=frequency,
        molecules_per_cell={s: molecule_time[s] / duration for s in mapping["surface_indices"]},
        occupied_fraction_by_species=inventory,
        coverage={k: sum(v.values()) for k, v in inventory.items()},
        pathway_flux=pathways,
        species_net_rate=dict(production),
    )


def seed_series(config, dataset, trajectory, mapping):
    """One full trajectory per native RNG seed. A continuation must be joined to its writer first."""
    c = config["zacros"]
    condition = {k: v for k, v in c.items() if k != "seed"}
    if any(trajectory[k][0][0] != 0 for k in ("procstat", "specnum")):
        raise ValueError("Continuation alone is not an independent seed")
    signature = sha256_json([dataset["dataset_version"], config["partial_pressure_bar"], condition])
    size_family = None
    # Reusing fixed native seed sites would change the initial coverage at another size.
    if "repeat_cell" in c and not c["seeds"]:
        size_family = sha256_json(
            [
                dataset["dataset_version"],
                config["partial_pressure_bar"],
                {k: v for k, v in condition.items() if k != "repeat_cell"},
            ]
        )
    return dict(
        size_family=size_family,
        seed=integer(c["seed"], "native seed"),
        condition=signature,
        trajectory=trajectory,
        dataset=dataset,
        mapping=mapping,
    )


def seed_precision(runs, *, start_s, end_s, observable, key, required_seeds, absolute_precision):
    """Two-sided 95% Student interval on independent trajectory means, with window sensitivity."""
    from scipy.stats import t as student_t

    integer(required_seeds, "planned replicate count", 2)
    target = finite_number(absolute_precision, "absolute precision", positive=True)
    if not runs or len({r["condition"] for r in runs}) != 1 or len({r["seed"] for r in runs}) != len(runs):
        raise ValueError("Replicates require identical model and conditions and unique seeds")
    if observable not in ("coverage", "molecules_per_cell", "event_frequency_s_inverse", "pathway_flux"):
        raise ValueError("Unknown ensemble observable")

    def measure(run, a, b):
        value = window_analysis(run["trajectory"], run["dataset"], run["mapping"], a, b)[observable][key]
        return value["net_rate"] if observable == "pathway_flux" else value

    middle = (start_s + end_s) / 2
    values = [measure(r, start_s, end_s) for r in runs]
    early = [measure(r, start_s, middle) for r in runs]
    late = [measure(r, middle, end_s) for r in runs]
    n = len(values)

    def half_width(data):
        return float(student_t.ppf(0.975, n - 1)) * stdev(data) / sqrt(n)

    half = half_width(values) if n > 1 else None
    delta = [b - a for a, b in zip(early, late, strict=True)]
    drift = mean(delta)
    drift_half = half_width(delta) if n > 1 else None
    informative = half is not None and half > 0
    precise = n >= required_seeds and informative and half <= target and abs(drift) + drift_half <= target
    center = mean(values)
    return dict(
        observable=observable,
        key=key,
        mean=center,
        seeds=[r["seed"] for r in runs],
        values=values,
        window_s=[start_s, end_s],
        first_half_mean=mean(early),
        second_half_mean=mean(late),
        drift=drift,
        drift_half_width=drift_half,
        half_width_95=half,
        interval_95=[center - half, center + half] if informative else None,
        decision="precision_met" if precise else "inconclusive",
        required_seeds=required_seeds,
        absolute_precision=target,
    )


def size_sensitivity(small, large, **design):
    """Compare intensive coverage at two periodic sizes with independent replicate groups."""
    from scipy.stats import t as student_t

    runs = [*small, *large]
    if (
        not small
        or not large
        or design["observable"] != "coverage"
        or not small[0]["size_family"]
        or len({r["size_family"] for r in runs}) != 1
        or len({r["seed"] for r in runs}) != len(runs)
    ):
        raise ValueError("Finite-size comparison requires matched periodic models and independent seeds")
    sizes = [group[0]["mapping"]["site_count"] for group in (small, large)]
    if sizes[1] <= sizes[0]:
        raise ValueError("Expected increasing lattice sizes")
    a, b = (seed_precision(group, **design) for group in (small, large))
    difference = b["mean"] - a["mean"]
    half = None
    if all(len(r["values"]) >= 2 for r in (a, b)):
        va, vb = (stdev(r["values"]) ** 2 / len(r["values"]) for r in (a, b))
        if va + vb > 0:
            df = (va + vb) ** 2 / (va**2 / (len(small) - 1) + vb**2 / (len(large) - 1))
            half = float(student_t.ppf(0.975, df)) * sqrt(va + vb)
    met = (
        all(r["decision"] == "precision_met" for r in (a, b))
        and half is not None
        and abs(difference) + half <= design["absolute_precision"]
    )
    return dict(
        site_counts=sizes,
        difference=difference,
        half_width_95=half,
        decision="within_tolerance" if met else "inconclusive",
        per_size=[a, b],
    )


def contact_flux(frames, processes, events, mapping):
    """Attribute only a single resolved two-site jump. Report unlocated native counts separately."""
    row_at = {step: counts for step, _, counts in processes}
    by_name = {r["native_step"]: e for r, e in zip(mapping["event_checks"], events, strict=True)}
    edges = {(i, j): c for i, j, c in mapping["topology"]["edges"]}
    resolved, unresolved = Counter(), Counter()
    previous = None
    for frame in frames:
        if previous is not None:
            a, b = previous["step"], frame["step"]
            if a not in row_at or b not in row_at or b <= a:
                raise ValueError("Contact flux requires ordered snapshots with matching process samples")
            changed = tuple(i for i in sorted(frame["sites"]) if frame["sites"][i] != previous["sites"][i])
            for name, count in row_at[b].items():
                delta = count - row_at[a][name]
                if not delta:
                    continue
                if delta < 0:
                    raise ValueError("Decreasing process counter")
                if b == a + 1 and len(by_name[name]["site_ids"]) == 2 and changed in edges and edges[changed]:
                    resolved[(name, *changed, edges[changed])] += delta
                else:
                    unresolved[name] += delta
        previous = frame
    return dict(
        resolved=[
            dict(native_step=k, left=i, right=j, interface_id=c, count=v)
            for (k, i, j, c), v in resolved.items()
        ],
        unresolved=dict(unresolved),
    )
