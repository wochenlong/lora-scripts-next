"""桌面 Rust 与训练器 Python 共用的网络策略合同；不访问公网。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mikazuki.networking.policy import original_proxy_env, redact, resolve_policy


VECTORS = json.loads(
    (Path(__file__).with_name("fixtures") / "launcher-network-policy-vectors.json").read_text(
        encoding="utf-8"
    )
)


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda case: case["id"])
def test_launcher_python_policy_shared_vectors(case):
    policy = resolve_policy(
        saved=case["saved"], environ=case["environ"], system=case["system"]
    )
    expected = case["expected"]
    for field, value in expected.items():
        assert getattr(policy, field) == value, (case["id"], field)
    for route in case["routes"]:
        assert policy.bypass(route["url"]) is route["bypass"], case["id"]
        assert policy.proxy_for(route["url"]) == route["proxy"], case["id"]

    base = dict(case["environ"], PATH="keep-path", UNRELATED="keep-value")
    child = policy.process_env(base)
    assert child["PATH"] == "keep-path"
    assert child["UNRELATED"] == "keep-value"
    assert not any(key.lower() == "all_proxy" for key in child)
    for name in ("http_proxy", "https_proxy"):
        if expected[name] is None or policy.mode == "direct":
            assert name not in child and name.upper() not in child
        else:
            assert child[name] == child[name.upper()] == expected[name]
    assert child["no_proxy"] == child["NO_PROXY"] == expected["no_proxy"]
    assert "fake-password" not in repr(policy)
    assert "fake-password" not in json.dumps(policy.diagnostic())


@pytest.mark.parametrize("case", VECTORS["errors"], ids=lambda case: case["id"])
def test_launcher_python_policy_shared_errors(case):
    with pytest.raises(ValueError):
        resolve_policy(saved=case["saved"], environ=case["environ"], system=case["system"])


@pytest.mark.parametrize("case", VECTORS["original_inputs"], ids=lambda case: case["id"])
def test_launcher_original_proxy_input_vectors(case):
    assert original_proxy_env(case["environ"]) == case["expected"]


@pytest.mark.parametrize("case", VECTORS["redact"])
def test_launcher_redaction_vectors(case):
    assert redact(case["input"]) == case["expected"]
