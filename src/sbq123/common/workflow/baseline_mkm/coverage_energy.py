"""Reviewed mean-field excess Gibbs energy and deterministic fixed-temperature MKM children."""

from sbq123.common.kinetic_model.replay_precision import same_recalculation
from copy import deepcopy

import numpy as np

from sbq123.common.artifacts.artifact_io import require_sha256, sha256_bytes, sha256_json
from sbq123.common.workflow.baseline_mkm.coverage_ts import displaced_gibbs, validate_record
from scripts.kinetic_parameters.engine import calculate, generate
from scripts.kinetic_parameters.export_contract import validate_export
from sbq123.common.workflow.multiphase_contracts import decode_unique_json
from sbq123.common.reaction_network.reaction_network.thermodynamics import check_cycles
from sbq123.common.validation.scientific_validation import validate_finite_tree


def system_identity(network):
    """Fit identity independent of the review envelope that cites the fit bytes."""
    return sha256_json(
        dict(
            project=network["project_id"],
            catalog=network["catalog"],
            species=network["species"],
            reactions=[r["definition"] for r in network["reactions"]],
        )
    )


class ExcessGibbs:
    """Immutable scientific inputs. x counts molecules per reviewed reference unit."""

    def __init__(self, network, parent, fit_text):
        validate_export(parent)
        bindings = dict(network_version=network["network_version"], models=[r["model"] for r in parent["reactions"]])
        if not same_recalculation(parent, generate(network, bindings)):
            raise ValueError("Expected an unmodified, reproducible kinetic parent")
        self.network, self.parent, self.fit_text = network, parent, fit_text
        raw = fit_text.encode("utf-8")
        self.digest = sha256_bytes(raw)
        fit = self.fit = decode_unique_json(raw)
        validate_record(fit, "coverage_excess_fit")
        if fit["system_sha256"] != system_identity(network):
            raise ValueError("Fit belongs to a different catalyst, structure, interface or reaction definition")
        verified = {s["sha256"] for s in network["source_artifacts"] if s["role"] == "verified_evidence"}
        if not {self.digest, fit["source_sha256"]} <= verified:
            raise ValueError("Interaction fit or source absent from verified network evidence")
        self.species = {s["species_id"]: s for s in network["species"]}
        self.entries = {e["definition"]["reaction_id"]: e for e in network["reactions"]}
        if self.entries.keys() != fit["reactions"].keys():
            raise ValueError("Explicit TS and parent Gibbs records required for every reaction")
        self.ids = [a["species_id"] for a in fit["axes"]]
        self.capacity, self.footprint = self._inventory()
        self.x0 = np.array([a["x0"] for a in fit["axes"]])
        self.domain = np.array([a["domain"] for a in fit["axes"]])
        self.W = self._matrix("W")
        self.sigma = self._matrix("W_sigma")
        self.check_x(self.x0)
        scales = {r["native_events_per_reference"] for r in fit["reactions"].values()} - {None}
        if len(scales) > 1:
            raise ValueError("All reaction fluxes must use the common native extent denominator")
        for row in parent["reactions"]:
            self._check_row(row)

    def _inventory(self):
        sites = self.fit["capacities"]
        surfaces = {s["species_id"] for s in self.species.values() if s["phase"] == "surface"}
        if len(set(self.ids)) != len(self.ids) or set(self.ids) != surfaces:
            raise ValueError("Axis order must identify each surface molecule once")
        if set(sites) != {s["site_id"] for s in self.network["catalog"]["sites"]}:
            raise ValueError("Inventory capacities differ from network")
        footprints = [self.species[s]["site_occupancy"] for s in self.ids]
        bases = [a["basis_inventory"] for a in self.fit["axes"]]
        if any(not f or b not in f or not f.keys() <= sites.keys() for f, b in zip(footprints, bases, strict=True)):
            raise ValueError("Missing molecular footprint or basis inventory")
        return np.array([sites[b] for b in bases]), np.array([[f.get(k, 0) for f in footprints] for k in sites])

    def _matrix(self, name):
        a = np.asarray(self.fit[name], dtype=float)
        if a.shape != (len(self.ids), len(self.ids)) or not np.array_equal(a, a.T):
            raise ValueError(f"{name} must be square and symmetric in ordered molecular coordinates")
        return a

    def _check_row(self, row):
        p, m = row["parameter_set"], row["model"]
        spec = self.fit["reactions"][row["reaction_id"]]
        if self.digest not in {s["sha256"] for s in m["sources"]} or self.fit["use_scope"] != m.get("use_scope", "project"):
            raise ValueError("Each reviewed kinetic model must cite the interaction fit in the same scope")
        if (self.fit["energy_reference_id"], self.fit["standard_state_id"]) != (p["energy_reference_id"], p["standard_state_id"]):
            raise ValueError("Interaction reference differs from kinetic reference")
        if p["coverage_terms"] or m.get("coverage_fractions") or row["coverage_shift_ev"] or "coverage_energy" in row:
            raise ValueError("Parent contains a previously applied coverage correction")
        if spec["parent_gibbs_eV"] != row["energies"]["gibbs_ev"] or not row["rates"]["reverse"]:
            raise ValueError("Expected the reviewed reversible Gibbs baseline at x0")
        for name in ("temperature_K", "pressure_Pa"):
            lo, hi = self.fit[name]
            if not lo <= p[name] <= hi:
                raise ValueError(f"Outside fit {name} domain")
        for key in ("absolute_TS_slope", "TS_slope_sigma"):
            if len(spec[key]) != len(self.ids):
                raise ValueError("TS vector differs from ordered molecular coordinates")

    def check_x(self, x):
        if x.shape != self.x0.shape or not np.all(np.isfinite(x)) or np.any(x < 0):
            raise ValueError("Invalid molecular coordinates")
        if np.any(x < self.domain[:, 0]) or np.any(x > self.domain[:, 1]):
            raise ValueError("Coverage outside reviewed domain")
        vacancy = 1 - (self.footprint @ x) / list(self.fit["capacities"].values())
        if np.any(vacancy < 0):
            raise ValueError("Coverage exceeds site inventory")
        return dict(zip(self.fit["capacities"], vacancy.tolist(), strict=True))

    def coordinates(self, theta):
        if set(theta) != set(self.ids) or any(type(v) not in (int, float) for v in theta.values()):
            raise ValueError("Supply finite molecular coverage per named inventory for every axis")
        x = self.capacity * np.asarray([theta[s] for s in self.ids], dtype=float)
        self.check_x(x)
        return x

    def fractions(self, x):
        return dict(zip(self.ids, (x / self.capacity).tolist(), strict=True))

    def activities(self, x):
        result = {}
        for axis, value in zip(self.fit["axes"], x, strict=True):
            sid, site = axis["species_id"], axis["activity_inventory"]
            footprint = self.species[sid]["site_occupancy"]
            if site not in footprint:
                raise ValueError(f"Missing reviewed fractional-occupation activity mapping for {sid}")
            result[sid] = float(footprint[site] * value / self.fit["capacities"][site])
        return result

    def energy(self, x):
        self.check_x(x)
        z = x - self.x0
        mu = self.W @ z
        return float(z @ mu / 2), mu

    def stoich(self, side):
        return np.asarray([side.get(s, 0) for s in self.ids])

    def barrier_derivatives(self, row):
        reaction = self.entries[row["reaction_id"]]["definition"]
        ts = self.fit["reactions"][row["reaction_id"]]["absolute_TS_slope"]
        return np.array([ts - self.stoich(reaction[key]) @ self.W for key in ("reactants", "products")])

    def _uncertainty(self, rid, side, z, with_ts):
        # Unique upper-triangular W parameters are independent. Wji and Wij are one parameter.
        coeff = np.outer(side, z)
        coeff = np.triu(coeff) + np.triu(coeff.T, 1)
        variance = np.sum((coeff * self.sigma) ** 2)
        if with_ts:
            variance += np.sum((self.fit["reactions"][rid]["TS_slope_sigma"] * z) ** 2)
        return float(np.sqrt(variance))

    def child(self, theta, previous=None, *, study_sha256=None):
        if study_sha256 is not None:
            require_sha256(study_sha256, label="coverage study manifest")
        if previous is not None:
            require_sha256(previous, label="preceding execution receipt")
        x = self.coordinates(theta)
        phi, mu = self.energy(x)
        child = deepcopy(self.parent)
        del child["dataset_version"]
        trace = dict(
            format="mkm-frozen-coverage/1",
            parent_version=self.parent["dataset_version"],
            study_sha256=study_sha256,
            fit_text=self.fit_text,
            fit_sha256=self.digest,
            evaluation_coverage=theta.copy(),
            previous_receipt_sha256=previous,
            excess_G_eV_per_reference=phi,
            chemical_potential_eV=dict(zip(self.ids, mu.tolist(), strict=True)),
        )
        child["coverage_iteration"] = trace
        entries = [self._apply(row, x - self.x0, mu) for row in child["reactions"]]
        check_cycles(entries)
        validate_finite_tree(child)
        return dict(child, dataset_version=sha256_json(child))

    def _apply(self, row, z, mu):
        rid = row["reaction_id"]
        entry = self.entries[rid]
        rx = entry["definition"]
        left, right = (self.stoich(rx[k]) for k in ("reactants", "products"))
        ts = float(self.fit["reactions"][rid]["absolute_TS_slope"] @ z)
        before = row["energies"]["gibbs_ev"]
        g = displaced_gibbs(before, float(left @ mu), ts, float(right @ mu))
        if min(g["forward"], g["reverse"]) < 0:
            raise ValueError("Negative derived barrier lacks a qualified barrierless law")
        row["energies"] = dict(row["energies"], gibbs_ev=g, thermal_basis="reviewed_mean_field_excess")
        view = dict(entry, energies=row["energies"])
        rates, row["equilibrium"], _ = calculate(view, row["parameter_set"], row["model"], self.species)
        row["coverage_energy"] = dict(
            fit_sha256=self.digest, parent_gibbs_eV=before, absolute_TS_shift_eV=ts, correction_sigma_eV={}, provenance="model_prediction"
        )
        for side, multiplicity in (("forward", left), ("reverse", right)):
            row["rates"][side].update(rates[side])
            row["rates"][side]["sigma_ln_k"] = None  # Joint covariance with the baseline is unspecified.
            row["coverage_energy"]["correction_sigma_eV"][side] = self._uncertainty(rid, multiplicity, z, True)
        row["coverage_energy"]["correction_sigma_eV"]["reaction"] = self._uncertainty(rid, right - left, z, False)
        row["scientifically_validated"] = False
        row["local_event_missing"] = ["Mean-field coverage child is qualified only for fixed-parameter MKM"]
        return view


def reconstruct_child(network, parent, record):
    if record["parent_version"] != parent["dataset_version"] or record["format"] != "mkm-frozen-coverage/1":
        raise ValueError("Coverage child parent or format differs")
    model = ExcessGibbs(network, parent, record["fit_text"])
    return model.child(record["evaluation_coverage"], record["previous_receipt_sha256"], study_sha256=record["study_sha256"])
