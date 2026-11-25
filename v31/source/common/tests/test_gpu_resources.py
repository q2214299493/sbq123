import subprocess

import pytest

from scripts import gpu_resources


@pytest.mark.parametrize("failed_backend", [None, "BUCT2", "BUCT3"])
def test_gpu_resources_checks_all_three_backends(monkeypatch, capsys, failed_backend):
    destinations = []

    def run(argv, *, input, **kwargs):
        destination = argv[-2]
        destinations.append(destination)
        assert argv[-1] == "sh -s -- /home/sbq/sbq"
        if destination == "buct2-gpu":
            name = "BUCT2"
        else:
            port = argv[argv.index("-p") + 1]
            assert port in {"36039", "57396"}
            name = "BUCT(sbq)" if port == "36039" else "BUCT3"
        assert "StrictHostKeyChecking=yes" in argv
        assert "BatchMode=yes" in argv
        assert b"\r" not in input
        assert b"--query-compute-apps=gpu_uuid" in input
        assert b"scontrol -d -o show node" in input
        if name == failed_backend:
            return subprocess.CompletedProcess(argv, 255, b"", b"Permission denied\n")
        return subprocess.CompletedProcess(argv, 0, b"GPUs: test snapshot\n", b"")

    monkeypatch.setattr(gpu_resources.subprocess, "run", run)
    assert gpu_resources.main([]) == (1 if failed_backend else 0)
    assert sorted(destinations) == ["buct2-gpu", "sbq@10sx4jr711576.vicp.fun", "sbq@10sx4jr711576.vicp.fun"]
    output = capsys.readouterr().out
    assert "[BUCT(sbq)] snapshot" in output
    for name in ("BUCT2", "BUCT3"):
        if name == failed_backend:
            assert f"[{name}] incomplete; availability unknown\nPermission denied" in output
        else:
            assert f"[{name}] snapshot" in output


@pytest.mark.parametrize("cpu_failure", [False, True])
def test_combined_pool_checks_cpu_without_gpu_commands(monkeypatch, capsys, cpu_failure):
    destinations = []

    def run(argv, *, input, **kwargs):
        destination = argv[-2]
        destinations.append(destination)
        if destination == "sunboquan-codex":
            assert argv[-1] == "sh -s -- /home_gkn/users/nsgkn_chengdj3"
            assert b"bhosts -w" in input and b"bqueues -w" in input
            assert b"nvidia-smi" not in input and b"\r" not in input
            if cpu_failure:
                raise subprocess.TimeoutExpired(argv, 20)
        else:
            assert b"nvidia-smi" in input
        return subprocess.CompletedProcess(argv, 0, b"resource snapshot\n", b"")

    monkeypatch.setattr(gpu_resources.subprocess, "run", run)
    assert gpu_resources.main(["--include-cpu"]) == int(cpu_failure)
    assert len(destinations) == 4
    assert destinations.count("sunboquan-codex") == 1
    output = capsys.readouterr().out
    assert "[BUCT3] snapshot" in output
    status = "incomplete; availability unknown" if cpu_failure else "snapshot"
    assert f"[sunboquan-codex (CPU)] {status}" in output
