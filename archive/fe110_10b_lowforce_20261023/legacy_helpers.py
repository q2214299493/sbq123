"""Exact legacy owner-function snapshot for this bounded data review only.

This does not add a production parser or override scientific admission rules.
FUNCTION_BINDINGS records original file and function-text hashes.
"""
from __future__ import annotations

import inspect
from decimal import Decimal
from itertools import permutations, product
from pathlib import Path

import numpy as np
from ase.geometry import find_mic

from scripts.adsorption.build_fe110_adsorption import expanded_symbols
from scripts.artifact_io import sha256_file
from scripts.vasp_result_gate import read_incar_values
from scripts.workflow_geometry import minimum_image_delta_xy

FUNCTION_BINDINGS = {'selected_steps': {'source': 'archive\\fe110_adsorption_pool_rebuild_20261019\\prepare_pool.py', 'source_sha256': '7027a4fee8a0c2b865534b31b93a798a567765a0dcc421b4cd138993c86a8532', 'function_sha256': '82046a797e544ddcb387179e3a8151378ea99152246f1162ab084fdadbb76386'}, 'reader_source': {'source': 'archive\\fe110_adsorption_pool_rebuild_20261019\\prepare_pool.py', 'source_sha256': '7027a4fee8a0c2b865534b31b93a798a567765a0dcc421b4cd138993c86a8532', 'function_sha256': '38b1e99f24ec163bff109b420563c09264ae927a48e535d605bb350a4866a377'}, 'check_inputs': {'source': 'archive\\fe110_adsorption_calibration_20261018\\prepare_current_trajectories.py', 'source_sha256': '2ad18ae309d5f3644f9c752cf8bd4e5b2157bf70de62fbe390437969a8b990cb', 'function_sha256': 'ebe143f5fc4e297e1938f7790d859655ff8839c23d62d57de548fc6c06400370'}, 'restore_input_lattice': {'source': 'archive\\fe110_adsorption_calibration_20261018\\prepare_current_trajectories.py', 'source_sha256': '2ad18ae309d5f3644f9c752cf8bd4e5b2157bf70de62fbe390437969a8b990cb', 'function_sha256': '6eb37350355b4233b7bd1f23ca7277271dc2b86b73088b0eecc5ecfbff4f2f02'}, 'verify_frame': {'source': 'archive\\fe110_adsorption_calibration_20261018\\reviewed_trajectory_helpers.py', 'source_sha256': 'd53e6e9640e2aaaa6d24412329b3a4df0fe5ed2cd6816050c97de338916213c2', 'function_sha256': '0538558924b7728f5c6607330016ad75adc25fe137907b20cd92682c8fbf8e17'}, 'collapse_redundant': {'source': 'archive\\fe110_adsorption_pool_rebuild_20261019\\prepare_pool.py', 'source_sha256': '7027a4fee8a0c2b865534b31b93a798a567765a0dcc421b4cd138993c86a8532', 'function_sha256': '9ac2293aeda9222481f5e416b26579ad9da5572ba10f0e42adf1fce33576b034'}, 'pose_variants': {'source': 'archive\\fe110_adsorption_pool_rebuild_20261019\\roles.py', 'source_sha256': 'a727f9c1dccbbd3bfba2abaa2b04ceb3c3d2a0bb5ad507c9663c6974ba0dd196', 'function_sha256': '0bb34e21cc62a6274e26da4b0e3f3bf577a50507b6105908119959920e6bfa09'}, 'pose_distance': {'source': 'archive\\fe110_adsorption_pool_rebuild_20261019\\roles.py', 'source_sha256': 'a727f9c1dccbbd3bfba2abaa2b04ceb3c3d2a0bb5ad507c9663c6974ba0dd196', 'function_sha256': '10b59bdc07c8ac09d92376d74323fbaa764c00cb85200d734f5e36fc73fa2299'}}

REMOTE_READER = "\nimport base64,hashlib,json,re,sys\nfrom pathlib import Path\nfor record in RECORDS:\n print('reading '+record['name'],file=sys.stderr,flush=True)\n root=Path(record['remote_dir'].replace('~',str(Path.home()),1)); out=root/'OUTCAR'\n before=out.stat(); h=hashlib.sha256(); frames=[]\n iteration=None; reached=False; current=None\n with out.open('rb') as f:\n  def line():\n   value=f.readline(); h.update(value); return value\n  while True:\n   offset=f.tell(); text=line()\n   if not text: break\n   match=re.search(rb'Iteration\\s+(\\d+)\\s*\\(\\s*(\\d+)\\s*\\)',text)\n   if match:\n    iteration=tuple(map(int,match.groups())); reached=False\n   if b'aborting loop because EDIFF is reached' in text: reached=True\n   if b'TOTAL-FORCE (eV/Angst)' in text:\n    raw=text; rows=[]; tokens=[]\n    while True:\n     value=line(); raw+=value; fields=value.split()\n     if len(fields)==6:\n      try: row=[float(v) for v in fields]\n      except ValueError: continue\n      rows.append(row); tokens.append([v.decode() for v in fields[:3]])\n     elif rows: break\n     elif not value: break\n    if not iteration or len(rows) not in (48,49): raise ValueError('invalid force frame')\n    current={'ionic_step':iteration[0],'electronic_iteration':iteration[1],\n             'EDIFF_marker_before_force':reached,'positions_A':[r[:3] for r in rows],\n             'position_tokens':tokens,'forces_eV_per_A':[r[3:] for r in rows],\n             'source_byte_range':[offset,f.tell()],'force_table_base64':base64.b64encode(raw).decode()}\n    frames.append(current)\n   if b'free  energy   TOTEN' in text and current is not None:\n    current['toten_eV']=float(text.split()[4])\n after=out.stat()\n if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns): raise ValueError('source changed')\n with out.open('rb') as f:\n  f.seek(max(0,before.st_size-100000)); tail=f.read(100000)\n if b'reached required accuracy' not in tail or b'General timing and accounting informations' not in tail:\n  raise ValueError('source not normally force-converged')\n total=frames[-1]['ionic_step']; wanted=set(selected_steps(total))\n files={}\n for name in ('POSCAR','CONTCAR','INCAR','KPOINTS','OSZICAR','XDATCAR'):\n  p=root/name\n  if p.stat().st_size>2000000: raise ValueError('source file exceeds inspection budget: '+name)\n  files[name]=base64.b64encode(p.read_bytes()).decode()\n print(json.dumps({'record':record,'frames':[r for r in frames if r['ionic_step'] in wanted],\n                   'total_steps':total,'OUTCAR_sha256':h.hexdigest(),'OUTCAR_bytes':before.st_size,\n                   'normal_completion':True,'files':files}),flush=True)\n"

def selected_steps(total):
    if total < 5:
        raise ValueError("trajectory too short")
    return sorted({1, 2, 3, 4, 5, total-1, total,
                   max(1, round(total*.25)), max(1, round(total*.5)), max(1, round(total*.75)),
                   *(round(1+(total-1)*i/15) for i in range(16))})


def reader_source(record: dict, version: int = 2) -> str:
    reader = REMOTE_READER
    changes = {
        "len(rows) not in (48,49)": "len(rows)!=record['atom_count']",
        "if b'reached required accuracy' not in tail or b'General timing and accounting informations' not in tail:":
            "if b'General timing and accounting informations' not in tail:",
        "'normal_completion':True,'files':files": "'normal_completion':True,'files':files,'ionic_converged':b'reached required accuracy' in tail,'POTCAR_sha256':hashlib.sha256((root/'POTCAR').read_bytes()).hexdigest()",
    }
    for old, new in changes.items():
        if reader.count(old) != 1:
            raise ValueError("reviewed reader version changed")
        reader = reader.replace(old, new)
    if version == 2:
        # Preserve byte ranges while avoiding one filesystem tell() per line.
        if reader.count("with out.open('rb') as f:") != 2 or reader.count("f.tell()") != 2:
            raise ValueError("reviewed reader IO layout changed")
        reader = reader.replace("out.open('rb')", "out.open('rb',buffering=1024*1024)")
        reader = reader.replace("  def line():", "  byte_cursor=[0]\n  def line():")
        reader = reader.replace("h.update(value); return value", "h.update(value); byte_cursor[0]+=len(value); return value")
        reader = reader.replace("f.tell()", "byte_cursor[0]")
    elif version != 1:
        raise ValueError("unknown reader version")
    return "RECORDS=" + repr([record]) + "\n" + inspect.getsource(selected_steps) + reader


def check_inputs(folder: Path, record: dict) -> None:
    for name in ("POSCAR", "INCAR", "KPOINTS"):
        if sha256_file(folder / name) != sha256_file(Path(record["workdir"]) / name):
            raise ValueError("submitted input changed: " + name)
    values = read_incar_values(folder / "INCAR")
    expected = {"ENCUT": 400, "ISPIN": 2, "ISMEAR": 1, "SIGMA": .2,
                "EDIFF": 1e-5, "EDIFFG": -.02, "ISIF": 2}
    if any(float(values[key]) != target for key, target in expected.items()) or values["GGA"] != "PE":
        raise ValueError("incompatible production branch")
    if values["LDIPOL"].strip(".").upper() not in ("FALSE", "F"):
        raise ValueError("dipole convention changed")
    moments = [float(value) for term in values["MAGMOM"].split()
               for value in ([term.split("*")[1]] * int(term.split("*")[0]) if "*" in term else [term])]
    if moments != [2.2] * 45 + [0.] * (record["atom_count"] - 45):
        raise ValueError("magnetic initialization changed")
    k = (folder / "KPOINTS").read_text().splitlines()
    if k[1].strip() != "0" or not k[2].lower().startswith("g") or k[3].split() != ["5", "5", "1"]:
        raise ValueError("kmesh changed")
    if any(float(value) for value in k[4].split()):
        raise ValueError("kmesh offset changed")


def restore_input_lattice(atoms, initial, xdatcar: Path) -> None:
    """ISIF2 keeps the input cell; XDATCAR prints only six lattice decimals."""
    with xdatcar.open(encoding="utf-8") as handle:
        header = [handle.readline() for _ in range(5)]
    scale = float(header[1])
    if scale <= 0:
        raise ValueError("unsupported XDATCAR lattice scale")
    bounds = np.asarray([[.5 * 10.0 ** Decimal(token).as_tuple().exponent
                          for token in line.split()] for line in header[2:5]]) * scale
    if bounds.shape != (3, 3) or np.any(np.abs(np.asarray(atoms.cell) - np.asarray(initial.cell)) > bounds + 1e-12):
        raise ValueError("XDATCAR cell differs beyond its printed precision")
    atoms.set_cell(initial.cell, scale_atoms=True)


def verify_frame(atoms, frame):
    positions = np.asarray(frame["positions_A"], dtype=float)
    forces = np.asarray(frame["forces_eV_per_A"], dtype=float)
    if positions.shape != (len(atoms), 3) or forces.shape != (len(atoms), 3):
        raise ValueError("Atom/force shape mismatch")
    if not np.isfinite(positions).all() or not np.isfinite(forces).all():
        raise ValueError("Nonfinite frame")
    _, delta = find_mic(positions - atoms.positions, atoms.cell, pbc=[True, True, False])
    precision = np.array([[len(t.split(".")[-1]) for t in row] for row in frame["position_tokens"]])
    bound = np.linalg.norm(0.5 * 10.0 ** (-precision), axis=1)
    if not np.all(delta <= bound + 1e-8):
        raise ValueError("Force geometry differs from exact structure beyond OUTCAR printing precision")
    if len(atoms.constraints) != 1 or list(atoms.constraints[0].get_indices()) != list(range(18)):
        raise ValueError("Unexpected fixed mask")
    return forces


def collapse_redundant(retained: list, distance) -> tuple[list, list]:
    """Collapse only same-job,near-geometry AND force-similar new frames."""
    redundant, kept = [], []
    for row in retained:
        match = None
        if row["origin"] == "expanded_closed_trajectory":
            for previous in kept:
                if previous["calculation_group"] != row["calculation_group"]:
                    continue
                delta = np.linalg.norm(np.asarray(row["forces_eV_per_A"])[18:]-np.asarray(previous["forces_eV_per_A"])[18:], axis=1).max()
                if delta <= .02 and distance(row, previous) <= .02:
                    match = previous["sample_id"]
                    break
        if match:
            redundant.append({"sample_id": row["sample_id"], "represented_by": match, "reason": "same_job_near_geometry_and_force"})
        else:
            kept.append(row)
    return kept, redundant


def pose_variants(pose, operations) -> np.ndarray:
    """Same-element permutations for leakage audit only; no stored atoms moved."""
    original_symbols = expanded_symbols(pose)[45:]
    canonical_order = sorted(range(len(original_symbols)), key=lambda i: original_symbols[i])
    symbols = [original_symbols[i] for i in canonical_order]
    coordinates = pose.frac[45:][canonical_order]
    by_symbol = [[i for i, v in enumerate(symbols) if v == s] for s in sorted(set(symbols))]
    orders = []
    for choices in product(*(permutations(indices) for indices in by_symbol)):
        order = list(range(len(symbols)))
        for indices, permutation in zip(by_symbol, choices, strict=True):
            for a, b in zip(indices, permutation, strict=True):
                order[a] = b
        orders.append(order)
    return np.asarray([(coordinates @ rotation.T + translation)[order]
                       for rotation, translation in operations for order in orders])


def pose_distance(first, second_variants) -> float:
    symbols = expanded_symbols(first)[45:]
    order = sorted(range(len(symbols)), key=lambda i: symbols[i])
    delta = minimum_image_delta_xy(second_variants-first.frac[45:][order]) @ first.cell
    return float(np.sqrt(np.min(np.mean(np.sum(delta**2, axis=-1), axis=-1))))
