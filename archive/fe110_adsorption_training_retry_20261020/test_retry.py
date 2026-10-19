import json

import pytest

from archive.fe110_adsorption_direct_training_20261020 import test_portable as fixtures
from scripts.adsorption import force_training_preflight as preflight
from scripts.adsorption.direct_training_arm import install_two_backward_guard

prepared = fixtures.prepared
fixture_manifest = fixtures.fixture_manifest


@pytest.mark.parametrize("difference,accepted", [(0., True), (1e-15, True), (2e-12, False)])
def test_canonical_roundtrip_positions_only(prepared, monkeypatch, difference, accepted):
    path, _ = prepared
    original = preflight.read
    def changed(*args, **kwargs):
        atoms = original(*args, **kwargs)
        atoms.positions[0, 0] += difference
        return atoms
    monkeypatch.setattr(preflight, "read", changed)
    if accepted:
        preflight.check_database_labels(path.parent, {"manifest_path": path.name})
    else:
        with pytest.raises(ValueError, match="coordinates"):
            preflight.check_database_labels(path.parent, {"manifest_path": path.name})


def test_canonical_roundtrip_still_requires_exact_forces(prepared):
    path, payload = prepared
    payload["splits"]["train"][0]["forces_eV_per_A"][18][0] += 1e-12
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="raw force"):
        preflight.check_database_labels(path.parent, {"manifest_path": path.name})


@pytest.mark.parametrize("link_energy", [True, False])
def test_two_backward_observer_counts_real_updates_without_extra_steps(tmp_path, link_energy):
    torch = pytest.importorskip("torch")
    class Trainer:
        def __init__(self):
            self.model = torch.nn.Module()
            self.model.output_heads = torch.nn.ModuleDict({"energy": torch.nn.Linear(2, 1), "forces": torch.nn.Linear(2, 3)})
            self.optimizer = torch.optim.SGD(self.model.parameters(), lr=1e-3)
            self.step = 0
        def _backward(self, loss):
            self.optimizer.zero_grad()
            loss.backward()
            self.optimizer.step()
        def train(self):
            for self.step in range(1, 4):
                features = torch.ones(1, 2)
                loss = self.model.output_heads["forces"](features).square().mean()
                if link_energy:
                    loss = loss + 0. * self.model.output_heads["energy"](features).sum()
                self._backward(loss)
            return "finished"
    install_two_backward_guard(Trainer, {"_request_sha256": "frozen-request"}, tmp_path)
    trainer = Trainer()
    if link_energy:
        assert trainer.train() == "finished" and trainer.step == 3
        record = json.loads((tmp_path / "native_two_backward_check.json").read_text())
        assert record["actual_optimizer_updates"] == 2 and record["extra_training_steps"] == 0
        assert [row["native_step"] for row in record["records"]] == [1, 2]
        assert trainer._direct_optimizer_updates == 3
    else:
        with pytest.raises(RuntimeError, match="zero-gradient"):
            trainer.train()
        assert not (tmp_path / "native_two_backward_check.json").exists()
