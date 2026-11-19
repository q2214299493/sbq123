"""Read one converged CATKINAS single point with frozen gas pressures and surface fractions."""
import argparse
import json
import re
from pathlib import Path

import numpy as np

from scripts.optional_dependencies import require_optional


def _vector(data, field):
    values = np.asarray(data.get(field))
    if values.ndim != 2 or values.shape[0] != 1 or values.dtype.kind not in "ifu" or not np.isfinite(values).all():
        raise ValueError(f"Expected one finite numeric sample in {field}")
    return values[0]


def _symbols(log, variable, prefix, values):
    matches = re.findall(rf"^\s*\[\s*{variable}\((\d+)\),\s*({prefix}\w+)\s*\]\s*$", log, re.MULTILINE)
    indices = [int(i) for i, _ in matches]
    names = [name for _, name in matches]
    if sorted(indices) != list(range(1, len(values)+1)) or len(set(names)) != len(names):
        raise ValueError(f"Missing or ambiguous {variable} symbol map")
    return {name: float(values[int(i)-1]) for i, name in matches}


def _gas_fluxes(log, values, pressures):
    # Rnets follows the reported gas-species table. params follows the x-symbol table.
    headers = [s.split() for s in log.splitlines() if s.lstrip().startswith("Species") and "(gas)" in s]
    if len(headers) != 1:
        raise ValueError("Missing or ambiguous gas flux table")
    names = [s.removesuffix("(gas)") for s in headers[0][1:]]
    if len(names) != len(values) or set(names) != {s.removeprefix("P_") for s in pressures} or len(set(names)) != len(names):
        raise ValueError("Inconsistent gas flux inventory")
    return dict(zip(names, values.tolist(), strict=True))


def read_single_point(mat_path, log_path):
    """Return constants, signed fluxes and labelled states from matching data1.mat / log1 files."""
    log = Path(log_path).read_bytes().decode("ascii", errors="replace")
    if (not re.search(r"Converged, return with the residue[^\r\n]*Succeed!!", log)
            or "CATKINAS is finished now" not in log):
        raise ValueError("Native log has no successful convergence record")
    fields = ("kf", "kr", "R", "Rnet", "y", "params", "Rnets", "Ean", "G0n")
    data = require_optional("scipy.io", "CATKINAS MAT result reading").loadmat(mat_path, variable_names=fields)
    kf, kr, net, ea, dg = (_vector(data, key) for key in ("kf", "kr", "Rnet", "Ean", "G0n"))
    n = len(kf)
    flux = np.asarray(data.get("R"))
    if (not n or any(len(v) != n for v in (kr, net, ea, dg)) or flux.shape != (1, n, 3)
            or flux.dtype.kind not in "ifu" or not np.isfinite(flux).all()):
        raise ValueError("Inconsistent native reaction result dimensions or values")
    forward, reverse, native_net = flux[0].T
    if np.any(kf <= 0) or np.any(kr <= 0) or np.any(forward < 0) or np.any(reverse < 0):
        raise ValueError("Nonphysical directional coefficients or fluxes")
    if not (np.allclose(native_net, net, rtol=1e-10, atol=1e-15) and
            np.all(abs(forward-reverse-net) <= 1e-10*np.maximum(forward+reverse, 1e-15))):
        raise ValueError("Inconsistent native net flux")
    coverages = _symbols(log, "y", "Q", _vector(data, "y"))
    pressures = _symbols(log, "x", "P_", _vector(data, "params"))
    gas_flux = _gas_fluxes(log, _vector(data, "Rnets"), pressures)
    if any(not 0 <= x <= 1 for x in coverages.values()) or any(x < 0 for x in pressures.values()):
        raise ValueError("Nonphysical coverage or pressure")
    columns = dict(kf=kf, kr=kr, forward_flux=forward, reverse_flux=reverse, net_flux=net,
                   applied_forward_barrier_eV=ea, applied_reaction_energy_eV=dg)
    return {"reactions": [dict(index=i+1, **{name: float(col[i]) for name, col in columns.items()}) for i in range(n)],
            "coverages": coverages, "partial_pressures_bar": pressures, "net_gas_flux_per_reference_site_s": gas_flux}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mat", type=Path)
    parser.add_argument("log", type=Path)
    args = parser.parse_args()
    print(json.dumps(read_single_point(args.mat, args.log), indent=2, allow_nan=False))
