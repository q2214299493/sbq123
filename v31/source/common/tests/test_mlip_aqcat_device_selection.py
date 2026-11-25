"""The shared AQCat loader must honor explicit CPU versus CUDA requests."""
from pathlib import Path
import sys
from types import ModuleType

import pytest

from scripts.mlip_same_structure_benchmark import _load_calculator


@pytest.mark.parametrize("device,cpu", [("cuda",False),("cuda:0",False),("cpu",True)])
def test_aqcat_loader_passes_explicit_cpu_flag(monkeypatch,device,cpu):
    captured={}
    sentinel=object()
    def patched_calc(**kwargs):
        captured.update(kwargs)
        return sentinel
    for name in ("fairchem","fairchem.core","fairchem.core.common","fairchem.core.common.relaxation",
                 "fairchem.core.models","fairchem.core.models.equiformer_v2"):
        module=ModuleType(name)
        module.__path__=[]
        monkeypatch.setitem(sys.modules,name,module)
    ase_utils=ModuleType("fairchem.core.common.relaxation.ase_utils")
    ase_utils.patched_calc=patched_calc
    monkeypatch.setitem(sys.modules,ase_utils.__name__,ase_utils)
    ev2=ModuleType("fairchem.core.models.equiformer_v2.equiformer_v2_film")
    monkeypatch.setitem(sys.modules,ev2.__name__,ev2)
    assert _load_calculator("aqcat25",Path("frozen.pt"),device) is sentinel
    assert captured=={"checkpoint_path":"frozen.pt","is_spin_off":False,"is_low_fi":False,"cpu":cpu}
