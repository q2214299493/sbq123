import subprocess

import pytest

from scripts import gpu_resources


@pytest.mark.parametrize("buct2_exit", [0, 255])
def test_gpu_resources_checks_both_backends(monkeypatch, capsys, buct2_exit):
    destinations = []

    def run(argv, *, input, **kwargs):
        destination = argv[-2]
        destinations.append(destination)
        assert argv[-1] == "sh -s -- /home/sbq/sbq"
        if destination != "buct2-gpu":
            assert argv[argv.index("-p") + 1] == "36039"
        assert "StrictHostKeyChecking=yes" in argv
        assert "BatchMode=yes" in argv
        assert b"\r" not in input
        assert b"--query-compute-apps=gpu_uuid" in input
        assert b"scontrol -d -o show node" in input
        if destination == "buct2-gpu" and buct2_exit:
            return subprocess.CompletedProcess(argv, buct2_exit, b"", b"Permission denied\n")
        return subprocess.CompletedProcess(argv, 0, b"GPUs: test snapshot\n", b"")

    monkeypatch.setattr(gpu_resources.subprocess, "run", run)
    assert gpu_resources.main([]) == (1 if buct2_exit else 0)
    assert sorted(destinations) == ["buct2-gpu", "sbq@10sx4jr711576.vicp.fun"]
    output = capsys.readouterr().out
    assert "[BUCT(sbq)] snapshot" in output
    if buct2_exit:
        assert "[BUCT2] incomplete; availability unknown\nPermission denied" in output
    else:
        assert "[BUCT2] snapshot" in output
