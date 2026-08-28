"""ai-toolkit launcher: driver handoff + TE override env."""

from pathlib import Path

from mikazuki.engines.ai_toolkit.launcher import build_train_spec
from mikazuki.engines.ai_toolkit.settings import RuntimeConfig


def _runtime(tmp_path: Path) -> RuntimeConfig:
    return RuntimeConfig(
        toolkit_root=tmp_path / "toolkit",
        python=tmp_path / "toolkit" / ".venv" / "bin" / "python",
        lora_next_root=tmp_path,
        output_dir=tmp_path / "output",
        logging_dir=tmp_path / "logs",
        cache_dir=tmp_path / ".cache",
    )


def test_spec_runs_driver_with_config(tmp_path, monkeypatch):
    monkeypatch.delenv("AI_TOOLKIT_TE_PATH", raising=False)
    config_yaml = tmp_path / "cfg.yaml"
    spec = build_train_spec(_runtime(tmp_path), config_yaml, "task-1")
    assert spec.command[0].endswith("python")
    assert spec.command[1].endswith("driver.py")
    assert spec.command[2] == str(config_yaml)
    assert spec.cwd == tmp_path / "toolkit"
    assert "AI_TOOLKIT_TE_PATH" not in spec.env
    assert spec.env["HF_HUB_DISABLE_XET"] == "1"


def test_spec_te_path_env(tmp_path):
    config_yaml = tmp_path / "cfg.yaml"
    spec = build_train_spec(_runtime(tmp_path), config_yaml, "task-1", te_path="/models/qwen3-4b")
    assert spec.env["AI_TOOLKIT_TE_PATH"] == "/models/qwen3-4b"


def test_spec_gpu_visibility(tmp_path):
    config_yaml = tmp_path / "cfg.yaml"
    spec = build_train_spec(_runtime(tmp_path), config_yaml, "task-1", gpu_ids=["1"])
    assert spec.env["CUDA_VISIBLE_DEVICES"] == "1"
