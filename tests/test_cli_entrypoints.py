from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_anima_cli_entrypoints_exist_and_point_to_dedicated_runtimes():
    standard = read("scripts/cli/train_anima_by_toml.sh")
    fast = read("scripts/cli/train_anima_fast_by_toml.sh")
    root_standard = read("train_anima_by_toml.sh")
    root_fast = read("train_anima_fast_by_toml.sh")

    assert "scripts/dev/anima_train_network.py" in standard
    assert "docs/examples/anima-lora-benchmark-kohya.toml" in standard
    assert "extensions/anima_lora/.venv" in fast
    assert "extensions/anima_lora/source/train.py" in fast
    assert "scripts/cli/train_anima_by_toml.sh" in root_standard
    assert "scripts/cli/train_anima_fast_by_toml.sh" in root_fast


def test_legacy_train_sh_points_anima_users_to_dedicated_scripts():
    script = read("train.sh")

    assert "legacy SD/SDXL/Flux LoRA CLI entry" in script
    assert "train_anima_by_toml.sh" in script
    assert "train_anima_fast_by_toml.sh" in script
    assert "scripts/cli/train.sh" in script


def test_readme_and_cli_docs_explain_anima_cli_entrypoints():
    readme = read("README.md")
    readme_zh = read("README-zh.md")
    cli_docs = read("docs/cli-args.md")
    anima_docs = read("docs/anima-training.md")

    for content in (readme, readme_zh, cli_docs, anima_docs):
        assert "train_anima_by_toml.sh" in content
        assert "train_anima_fast_by_toml.sh" in content

    assert "qwen3" in cli_docs
    assert "qwen3" in anima_docs


def test_engine_installers_use_uv_cache_by_default():
    for path in (
        "mikazuki/engines/anima_fast/environment.py",
        "mikazuki/engines/musubi/environment.py",
        "mikazuki/engines/ai_toolkit/environment.py",
    ):
        assert '"--no-cache"' not in read(path), path


def test_clear_cache_scripts_exist_and_call_uv_cache_clean():
    sh = read("clear_cache.sh")
    bat = read("clear_cache.bat")

    assert "uv cache clean" in sh
    assert "uv cache clean" in bat
