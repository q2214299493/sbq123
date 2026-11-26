"""Check fixed-T microscopic coefficients and optional reviewed local TS predictions."""

import math
from collections import Counter, defaultdict

import numpy as np

from scripts.kinetic_parameters.engine import reviewed
from scripts.kinetic_parameters.laws import exp_rate
from scripts.kinetic_parameters.prediction import covariance
from scripts.scientific_validation import finite_number
from scripts.physical_constants import KB


def _barrier(fit, row):
    """A local linear Gibbs barrier at the bound condition; axes and coefficients use eV."""
    p = row["parameter_set"]
    sources = {s["sha256"] for s in row["model"]["sources"]}
    if (
        fit["basis"] != "isolated_activation_gibbs_eV"
        or fit["energy_reference_id"] != p["energy_reference_id"]
        or fit["temperature_K"] != p["temperature_K"]
        or fit["pressure_Pa"] != p["pressure_Pa"]
        or not {fit["training_sha256"], fit["validation_sha256"]} <= sources
    ):
        raise ValueError("Unbound local fit evidence, conditions or energy reference")
    axes = fit["axes"]
    if not axes or len({a["name"] for a in axes}) != len(axes):
        raise ValueError("Missing or duplicate fit axes")
    x = []
    for axis in axes:
        value = finite_number(axis["value_eV"], "descriptor")
        lo, hi = axis["domain_eV"]
        if not lo <= value <= hi or axis["source_sha256"] not in sources:
            raise ValueError("Local descriptor outside reviewed domain or source")
        x.append(value)
    if fit["kind"] == "bep":
        if [a["name"] for a in axes] != ["reaction_gibbs"] or x != [row["energies"]["gibbs_ev"]["reaction"]]:
            raise ValueError("BEP requires this reaction's Gibbs energy")
    elif fit["kind"] != "linear_descriptor":
        raise ValueError("Unsupported local barrier fit")
    design = np.array([1.0, *x])
    coeff = np.array(fit["coefficients"])
    if coeff.shape != design.shape:
        raise ValueError("Local fit coefficient dimensions differ")
    # Conditional on fixed descriptors. Parameter uncertainty and residual scatter only.
    matrix = covariance(fit["coefficient_covariance"], len(design))
    residual = finite_number(fit["residual_sigma_eV"], "residual sigma", nonnegative=True)
    return finite_number(design @ coeff, "fitted barrier", nonnegative=True), math.sqrt(
        max(0.0, float(design @ matrix @ design)) + residual**2
    )


def _environment(e, env, species):
    """Append fixed spectator molecules and vacancies to both sides of the native pattern."""
    labels = env["site_ids"]
    if not labels or len(labels) != len(env["state"]):
        raise ValueError("Invalid local environment dimensions")
    base = len(e["site_ids"])
    offset = max((slot[1] for side in ("initial", "final") for slot in e[side] if slot), default=0)
    spectators, groups = [], defaultdict(list)
    for site, slot in zip(labels, env["state"], strict=True):
        if slot is None:
            spectators.append(None)
        else:
            sid, entity = slot
            if type(entity) is not int or entity < 1 or sid not in species:
                raise ValueError("Invalid local environment entity")
            groups[entity].append((sid, site))
            spectators.append([sid, offset + entity])
    for parts in groups.values():
        sid = parts[0][0]
        if any(s != sid for s, _ in parts) or Counter(k for _, k in parts) != species[sid]["site_occupancy"]:
            raise ValueError("Invalid spectator footprint")
    edges = env["neighbors_zero_based"]
    if not edges or any(max(i, j) < base for i, j in edges):
        raise ValueError("Environment must link additional slots to the event")
    e.update(
        initial=e["initial"] + spectators,
        final=e["final"] + spectators,
        site_ids=e["site_ids"] + labels,
        neighbors_zero_based=e["neighbors_zero_based"] + edges,
    )


def _observed_balance(row, pair):
    """Test paired per-embedding coefficients for an independently measured local energy change."""
    local = row["model"]["local_event"]
    p = row["parameter_set"]
    temperature = p["temperature_K"]
    standard_bar = p["standard_states"]["gas_pressure_Pa"] / 100000
    valid_sources = {s["sha256"] for s in row["model"]["sources"]}
    observed = {}
    for sample in local["balance_observations"]:
        environment = sample["environment_id"]
        if (
            not environment
            or environment in observed
            or sample["source_sha256"] not in valid_sources
            or sample["temperature_K"] != temperature
            or sample["energetics_sha256"] != local.get("energetics_sha256")
            or set(pair) != {"forward", "reverse"}
        ):
            raise ValueError("Invalid local detailed-balance evidence or model binding")
        logs = {}
        for direction, event in pair.items():
            entry = sample[direction]
            if entry["unit"] != event["unit"]:
                raise ValueError("Environment rate coefficient unit differs")
            k = finite_number(entry["coefficient"], "per-embedding rate", positive=True)
            logs[direction] = math.log(k) + sum(event["gas_partial_pressure_orders"].values()) * math.log(
                standard_bar
            )
        shift = finite_number(sample["local_reaction_energy_shift_eV"], "local energy change")
        if shift and not local.get("energetics_sha256"):
            raise ValueError("Local energy shift requires a bound energetics model")
        expected = row["equilibrium"]["ln_K_standard"] - shift / (KB * temperature)
        residual = logs["forward"] - logs["reverse"] - expected
        if abs(residual) > 1e-6:
            raise ValueError("Detailed balance fails in supplied local environment")
        observed[environment] = dict(log_ratio_residual=residual, source_sha256=sample["source_sha256"])
    if not observed:
        raise ValueError("Missing environment observations")
    return observed


def qualify_events(dataset, table):
    rows = {r["reaction_id"]: r for r in dataset["reactions"]}
    species = {s["species_id"]: s for s in dataset["species"]}
    logs = {}
    pairs = defaultdict(dict)
    for e in table["events"]:
        rid, direction = e["reaction_id"], e["direction"]
        pairs[rid][direction] = e
        r = rows[rid]
        local = r["model"]["local_event"]
        fit = local.get("barrier_fit")
        rate = r["rates"][direction]
        if fit is not None or "environment" in local or "balance_observations" in local:
            if not reviewed(
                r["model"], dataset["network_version"], {a["sha256"] for a in dataset["source_artifacts"]}
            ):
                raise ValueError("Local pattern or fit lacks event-specific scientific review")
        if "environment" in local:
            _environment(e, local["environment"], species)
        if fit is not None:
            if (
                local.get("coefficient_basis") != "isolated_reactants"
                or local.get("energetics_sha256")
                or r["coverage_shift_ev"]
                or r["model"].get("coverage_fractions")
            ):
                raise ValueError("Local fit requires isolated uncorrected kinetics")
            barrier, sigma = _barrier(fit, r)
            if r["direction"]["status"] == "reversible" and barrier < r["energies"]["gibbs_ev"]["reaction"]:
                raise ValueError("Fitted TS lies below the reverse reference state")
            # Replace only the forward TS height. The same TS displacement applies to reverse.
            original = r["rates"]["forward"]["activation_free_energy_ev"]
            kbt = KB * e["T_K"]
            e["pre_expon"] = exp_rate(math.log(e["pre_expon"]) - (barrier - original) / kbt)
            e["local_prediction"] = dict(
                barrier_eV=barrier,
                conditional_sigma_ln_k=sigma / kbt,
                training_sha256=fit["training_sha256"],
                validation_sha256=fit["validation_sha256"],
            )
        if rate.get("sigma_ln_k") is not None:
            e["upstream_sigma_ln_k"] = rate["sigma_ln_k"]
        p0_bar = r["parameter_set"]["standard_states"]["gas_pressure_Pa"] / 100000
        logs.setdefault(rid, {})[direction] = (
            math.log(e["pre_expon"])
            + sum(e["gas_partial_pressure_orders"].values()) * math.log(p0_bar)
            - e["activ_eng_eV"] / (KB * e["T_K"])
        )
    for rid, r in rows.items():
        status = r["direction"]["status"]
        wanted = {"forward", "reverse"} if status == "reversible" else {"forward"}
        pair = logs.get(rid, {})
        if status not in ("reversible", "irreversible") or set(pair) != wanted:
            raise ValueError("Missing or unknown event direction")
        if status == "reversible":
            target = r["equilibrium"]["ln_K_standard"]
            if target is None or abs(pair["forward"] - pair["reverse"] - target) > 1e-6:
                raise ValueError("Detailed balance fails per embedding at standard activities")
        if "balance_observations" in r["model"]["local_event"]:
            table.setdefault("environment_balance", {})[rid] = _observed_balance(r, pairs[rid])
    return table
