import sys
from types import SimpleNamespace

from mikazuki.utils import devices


def test_gui_without_torch_uses_nvml_labels_without_duplicates(monkeypatch):
    calls = []
    nvml = SimpleNamespace(
        nvmlInit=lambda: calls.append('init'),
        nvmlShutdown=lambda: calls.append('shutdown'),
        nvmlDeviceGetCount=lambda: 1,
        nvmlDeviceGetHandleByIndex=lambda index: index,
        nvmlDeviceGetName=lambda handle: b'Test GPU',
        nvmlDeviceGetMemoryInfo=lambda handle: SimpleNamespace(total=8 * 1024**3),
    )
    monkeypatch.setitem(sys.modules, 'torch', None)
    monkeypatch.setitem(sys.modules, 'pynvml', nvml)
    monkeypatch.setattr(devices, 'available_devices', [])
    monkeypatch.setattr(devices, 'printable_devices', [])
    devices.check_torch_gpu()
    devices.check_torch_gpu()
    assert devices.available_devices == [0]
    assert devices.printable_devices == ['GPU 0: Test GPU (8 GB)']
    assert calls == ['init', 'shutdown', 'init', 'shutdown']


def test_gui_without_torch_or_nvml_remains_available(monkeypatch):
    monkeypatch.setitem(sys.modules, 'torch', None)
    monkeypatch.setitem(sys.modules, 'pynvml', None)
    monkeypatch.setattr(devices, 'available_devices', ['stale'])
    monkeypatch.setattr(devices, 'printable_devices', ['stale'])
    devices.check_torch_gpu()
    assert devices.available_devices == []
    assert devices.printable_devices == []
