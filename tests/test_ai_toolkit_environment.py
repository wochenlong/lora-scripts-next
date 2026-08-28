"""ai-toolkit environment: platform-unsupported pin stripping (KNOWN_PITFALLS P5)."""

from pathlib import Path

from mikazuki.engines.ai_toolkit import environment


def test_prepare_requirements_strips_nested_pin(tmp_path):
    (tmp_path / "requirements_base.txt").write_text(
        "torch==2.11.0\ntorchcodec==0.9.1\nnumpy>=2,<3\n", encoding="utf-8"
    )
    (tmp_path / "dgx_requirements.txt").write_text(
        "-r requirements_base.txt\nscipy==1.16.0\n", encoding="utf-8"
    )
    out = environment.prepare_requirements(tmp_path, tmp_path / "work")
    assert out.name == ".dgx_requirements.platform-filtered.txt"
    top = out.read_text(encoding="utf-8")
    assert "scipy==1.16.0" in top
    assert "torchcodec" not in top
    included = Path(top.split("-r ", 1)[1].splitlines()[0])
    included_text = included.read_text(encoding="utf-8")
    assert "torchcodec" not in included_text
    assert "numpy>=2,<3" in included_text


def test_prepare_requirements_passthrough_without_match(tmp_path):
    (tmp_path / "requirements_base.txt").write_text("numpy>=2,<3\n", encoding="utf-8")
    out = environment.prepare_requirements(tmp_path, tmp_path / "work")
    assert out == tmp_path / "requirements_base.txt"


def test_prepare_requirements_passthrough_off_platform(monkeypatch, tmp_path):
    monkeypatch.setattr(environment, "_needs_pin_strip", lambda: False)
    (tmp_path / "requirements_base.txt").write_text("torchcodec==0.9.1\n", encoding="utf-8")
    out = environment.prepare_requirements(tmp_path, tmp_path / "work")
    assert out == tmp_path / "requirements_base.txt"
