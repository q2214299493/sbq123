"""Small synthetic progress parsing only; no scheduler or VASP execution."""
import importlib.util
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / 'archive/chco_paper_aqcat25_20261112/monitor_static_label.py'
spec = importlib.util.spec_from_file_location('static_label_monitor_tests', SOURCE)
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


def test_latest_live_rows_keep_stdout_iteration_and_real_energy_deltas():
    text = 'VASP header\nDAV: 1 -1.23D+02 -2.0D+00 -3.0D+00 100\nRMM: 2 -1.24E+02 -1.0E+00 -1.0E-01 200\n'
    rows = monitor.electronic_rows(text)
    assert rows[-1] == {'algorithm': 'RMM', 'step': 2, 'energy_eV': -124.0, 'delta_e_eV': -1.0, 'delta_eps_eV': -0.1}


def test_empty_headers_and_invalid_rows_do_not_claim_an_electronic_step():
    assert monitor.electronic_rows('vasp.6.4.2\nDAV: BAD *****\n') == []


def test_nonfinite_progress_is_explicit_and_keeps_JSON_finite():
    row = monitor.electronic_rows('DAV: 5 NaN 1.0 Infinity 100')[-1]
    assert row['step'] == 5 and row['energy_eV'] is None and row['delta_eps_eV'] is None
    assert row['nonfinite_energy_values'] is True
