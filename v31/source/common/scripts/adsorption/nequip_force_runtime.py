"""NequIP 0.19.1 adapter for the existing per-graph movable-force objective."""
import torch
from torchmetrics import Metric
from lightning.pytorch import Callback
from nequip.data import AtomicDataDict, register_fields
from nequip.data.dataset import ASEDataset

WEIGHTS = "force_loss_weights"
register_fields(node_fields=[WEIGHTS])


class MovableASEDataset(ASEDataset):
    def __init__(self, file_path, transforms=None):
        super().__init__(file_path=file_path, transforms=transforms or [], include_keys=[WEIGHTS],
            exclude_keys=["total_energy", "free_energy", "stress"])


class MovableForceVectorMAE(Metric):
    """Per-graph weighted force error:uniform train,original role-weighted dev."""
    full_state_update = False
    is_differentiable = True
    higher_is_better = False

    def __init__(self):
        super().__init__()
        self.add_state("total", default=torch.tensor(0.), dist_reduce_fx="sum")
        self.add_state("graphs", default=torch.tensor(0, dtype=torch.long), dist_reduce_fx="sum")

    def update(self, preds, target):
        reference = target[AtomicDataDict.FORCE_KEY]
        prediction = preds[AtomicDataDict.FORCE_KEY]
        weights = target[WEIGHTS].reshape(-1)
        batch = target[AtomicDataDict.BATCH_KEY].reshape(-1)
        if reference.shape != prediction.shape or reference.shape != (len(weights), 3):
            raise ValueError("force shapes differ")
        if not all(bool(torch.isfinite(x).all()) for x in [reference, prediction, weights]) or bool((weights < 0).any()):
            raise ValueError("nonfinite force or invalid mask")
        count = int(target[AtomicDataDict.NUM_NODES_KEY].numel())
        normalization = weights.new_zeros(count).index_add(0, batch, weights)
        if not torch.allclose(normalization, torch.ones_like(normalization), rtol=1e-6, atol=1e-7):
            raise ValueError("each graph must have normalized movable weights")
        errors = torch.linalg.vector_norm(prediction - reference, dim=-1)
        self.total = self.total + (weights * errors).sum()
        self.graphs = self.graphs + count

    def compute(self):
        return self.total / self.graphs


class CUDAEvidence(Callback):
    """Record actual CUDA placement in the authorized training process."""
    def on_train_start(self, trainer, pl_module):
        import os
        from pathlib import Path
        from scripts.artifact_io import write_json_exclusive
        device = next(pl_module.parameters()).device
        visible = os.environ.get("CUDA_VISIBLE_DEVICES", "")
        if device.type != "cuda" or not visible.startswith("GPU-") or "," in visible:
            raise ValueError("native training must bind one physical CUDA GPU")
        torch.cuda.set_per_process_memory_fraction(16384 * 1024**2 / torch.cuda.get_device_properties(device).total_memory, device)
        write_json_exclusive(Path(trainer.default_root_dir) / "model_device.json", {
            "device": str(device), "physical_gpu_uuid": visible, "parameter_count": sum(p.numel() for p in pl_module.parameters()),
            "request_sha256": os.environ["FE110_NEQUIP_REQUEST_SHA256"], "checkpoint_promoted": False})
