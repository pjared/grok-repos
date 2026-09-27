"""Accelerator choice. The graphics-card model is never read or stored."""

from __future__ import annotations

from types import SimpleNamespace

from suit_o.voice.runtime import (
    describe_accelerator,
    synthesis_device,
    torch_inference_device,
)


class _Cuda:
    def __init__(self, available: bool) -> None:
        self._available = available
        self.name_reads = 0

    def is_available(self) -> bool:
        return self._available

    def get_device_name(self, index: int) -> str:
        self.name_reads += 1
        raise AssertionError("the graphics card model must not be read")


def test_nvidia_cuda_is_named_without_the_card():
    device, summary = describe_accelerator(True, False, directml=False)
    assert device == "cuda"
    assert "NVIDIA CUDA" in summary
    assert "Radeon" not in summary
    assert "GeForce" not in summary


def test_rocm_uses_the_cuda_api_and_says_so():
    device, summary = describe_accelerator(True, True, directml=False)
    assert device == "rocm"
    assert "ROCm" in summary
    assert "NVIDIA" not in summary


def test_directml_leaves_chatterbox_on_cpu():
    device, summary = describe_accelerator(False, False, directml=True)
    assert device == "cpu"
    assert "DirectML" in summary
    assert "CPU" in summary
    assert "does not use it" in summary


def test_cpu_is_the_fallback_when_no_accelerator_is_present():
    device, summary = describe_accelerator(False, False, directml=False)
    assert device == "cpu"
    assert "CPU" in summary
    assert "DirectML" in summary


def test_torch_flags_do_not_read_the_card_name():
    cuda = _Cuda(True)
    torch_module = SimpleNamespace(cuda=cuda, version=SimpleNamespace(hip=None, cuda="12.4"))
    assert torch_inference_device(torch_module) == "cuda"
    assert cuda.name_reads == 0

    rocm = _Cuda(True)
    rocm_torch = SimpleNamespace(cuda=rocm, version=SimpleNamespace(hip="6.2", cuda=None))
    assert torch_inference_device(rocm_torch) == "cuda"
    assert rocm.name_reads == 0

    cpu = _Cuda(False)
    cpu_torch = SimpleNamespace(cuda=cpu, version=SimpleNamespace(hip=None, cuda=None))
    assert torch_inference_device(cpu_torch) == "cpu"
    assert cpu.name_reads == 0


def test_synthesis_device_maps_rocm_to_cuda(monkeypatch):
    from suit_o.voice.runtime import RuntimeStatus

    monkeypatch.setattr(
        "suit_o.voice.runtime.runtime_status",
        lambda: RuntimeStatus(True, "rocm", "Chatterbox on AMD ROCm."),
    )
    assert synthesis_device() == "cuda"
