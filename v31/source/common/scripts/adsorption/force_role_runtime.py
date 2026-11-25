"""Torch loss and resumable single-process sampler; never load a force model."""
import math

import torch


def graph_role_losses(prediction, reference, weights, fixed, natoms):
    if prediction.ndim != 2 or prediction.shape[1] != 3 or reference.shape != prediction.shape:
        raise ValueError("force tensor shape mismatch")
    n = len(prediction)
    if weights.shape != (n,) or fixed.shape != (n,) or natoms.ndim != 1:
        raise ValueError("role tensor shape mismatch")
    if natoms.dtype not in (torch.int32, torch.int64) or torch.any(natoms <= 0) or int(natoms.sum()) != n:
        raise ValueError("invalid graph atom counts")
    if not all(bool(torch.isfinite(t).all()) for t in (prediction, reference, weights)):
        raise ValueError("nonfinite force/weight")
    if torch.any((fixed != 0) & (fixed != 1)) or torch.any(weights[fixed != 0] != 0) or torch.any(weights[fixed == 0] <= 0):
        raise ValueError("role weights do not respect fixed mask")
    if not all(t.is_floating_point() for t in (prediction, reference, weights)):
        raise ValueError("force/weight tensors must be floating point")
    # AMP model outputs may be half precision; static weights must not be
    # quantized to half and mixed-dtype dot products must not reach training.
    dtype = torch.promote_types(prediction.dtype, reference.dtype)
    if dtype in (torch.float16, torch.bfloat16):
        dtype = torch.float32
    prediction, reference, weights = (t.to(dtype=dtype) for t in (prediction, reference, weights))
    counts = natoms.detach().cpu().tolist()
    errors = torch.linalg.vector_norm(prediction - reference, dim=-1)
    values = []
    for w, error in zip(weights.split(counts), errors.split(counts), strict=True):
        if not torch.isclose(w.sum(), w.new_tensor(1.), rtol=1e-6, atol=1e-7):
            raise ValueError("weights are not normalized per graph")
        values.append(torch.sum(w * error))
    return torch.stack(values)


def grouped_force_loss(prediction, reference, weights, fixed, natoms):
    return graph_role_losses(prediction, reference, weights, fixed, natoms).mean()


class RoleBatchSampler:
    """Sampling with replacement,one dataset-length epoch,exact resume sequence."""
    def __init__(self, probabilities, batch_size: int, seed: int):
        self.weights = torch.as_tensor(probabilities, dtype=torch.float64, device="cpu").clone()
        if self.weights.ndim != 1 or not len(self.weights) or not torch.isfinite(self.weights).all() or torch.any(self.weights <= 0):
            raise ValueError("invalid sampler probabilities")
        if not torch.isclose(self.weights.sum(), self.weights.new_tensor(1.), rtol=0, atol=1e-12):
            raise ValueError("sampler probabilities must sum to one")
        if not isinstance(batch_size, int) or batch_size <= 0 or not isinstance(seed, int) or seed < 0:
            raise ValueError("invalid batch size/seed")
        self.batch_size, self.seed = batch_size, seed
        self.epoch, self.start_iteration = 0, 0

    def __len__(self):
        return math.ceil(len(self.weights) / self.batch_size)

    def set_epoch_and_start_iteration(self, epoch: int, start_iteration: int):
        if not isinstance(epoch, int) or epoch < 0 or not isinstance(start_iteration, int) or not 0 <= start_iteration <= len(self):
            raise ValueError("invalid sampler resume cursor")
        self.epoch, self.start_iteration = epoch, start_iteration

    def set_epoch(self, epoch: int):
        self.set_epoch_and_start_iteration(epoch, 0)

    def __iter__(self):
        generator = torch.Generator(device="cpu").manual_seed(self.seed + self.epoch)
        indices = torch.multinomial(self.weights, len(self.weights), replacement=True, generator=generator).tolist()
        for start in range(self.start_iteration * self.batch_size, len(indices), self.batch_size):
            yield indices[start:start + self.batch_size]

