"""Opt-in Fairchem adapter; no changes to the default or deployed trainer."""
import numpy as np
import torch
from fairchem.core.models.equiformer_v2.trainers.forces_trainer import EquiformerV2ForcesTrainer

from scripts.adsorption.force_role_data import ROLE_IDS
from scripts.adsorption.force_role_runtime import RoleBatchSampler, graph_role_losses, grouped_force_loss


class RoleForceTrainer(EquiformerV2ForcesTrainer):
    def get_sampler(self, dataset, batch_size: int, shuffle: bool):
        if self.config["optim"].get("grouped_force_objective") is not True:
            raise ValueError("grouped force objective must be explicitly enabled")
        if not shuffle:
            return super().get_sampler(dataset, batch_size, shuffle)
        if torch.distributed.is_initialized() and torch.distributed.get_world_size() != 1:
            raise ValueError("role sampler supports one process only")
        # Subset.get_metadata maps shuffled subset positions to actual source rows.
        probabilities = dataset.get_metadata("adsorption_sampling_probability", np.arange(len(dataset)))
        if probabilities is None:
            raise ValueError("training sampling metadata missing")
        return RoleBatchSampler(probabilities, batch_size, self.config["cmd"]["seed"])

    def _compute_loss(self, out, batch):
        coefficients = {name: info["coefficient"] for name, info in self.loss_functions}
        if coefficients.get("forces") != 1 or coefficients.get("energy", 0) != 0 or set(coefficients) - {"forces", "energy"}:
            raise ValueError("role trainer supports force-only objective")
        target = batch.forces
        if "forces" in self.elementrefs:
            raise ValueError("force element references are unsupported")
        if "forces" in self.normalizers:
            target = self.normalizers["forces"].norm(target)
        return grouped_force_loss(out["forces"], target, batch.adsorption_force_weights.to(device=out["forces"].device), batch.fixed, batch.natoms)

    def _compute_metrics(self, out, batch, evaluator, metrics=None):
        metrics = super()._compute_metrics(out, batch, evaluator, metrics)
        predicted = self._denorm_preds("forces", out["forces"], batch)
        weights = batch.adsorption_force_weights.to(device=predicted.device)
        values = graph_role_losses(predicted, batch.forces, weights, batch.fixed, batch.natoms)
        metrics = evaluator.update("forces_role_vector_mae", {"total": float(values.sum()), "numel": len(values)}, metrics)
        errors = torch.linalg.vector_norm(predicted - batch.forces, dim=-1)
        for role, code in ROLE_IDS.items():
            mask = (batch.adsorption_force_roles == code) & (batch.fixed == 0)
            if mask.any():
                metrics = evaluator.update("forces_" + role + "_vector_mae", {"total": float(errors[mask].sum()), "numel": int(mask.sum())}, metrics)
        replay = torch.repeat_interleave(batch.adsorption_replay.bool(), batch.natoms) & (batch.fixed == 0)
        if replay.any():
            metrics = evaluator.update("forces_replay_vector_mae", {"total": float(errors[replay].sum()), "numel": int(replay.sum())}, metrics)
        return metrics

