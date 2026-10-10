import socket
import os
import sys
import types
import ast
import asyncio
from pathlib import Path
from unittest import mock

import pytest

import gui
from mikazuki import startup_settings as startup


def resolve(settings=None, argv=(), probe=lambda host, port: True):
    return startup.resolve_startup(settings or {}, gui.parser.parse_args(argv), probe=probe)


def test_defaults():
    config = resolve()
    assert (config.gui.host, config.gui.port, config.gui.port_conflict) == ("127.0.0.1", 28000, "error")
    assert config.open_browser is None
    assert not config.tensorboard.enabled
    assert config.tensorboard.port == 6007
    assert config.monitor.enabled
    assert (config.monitor.host, config.monitor.port) == ("127.0.0.1", 6008)


def test_settings_and_explicit_cli_precedence():
    settings = {"startup": {
        "gui": {"host": "::1", "port": 29000, "open_browser": False},
        "tensorboard": {"enabled": True, "port": 7000},
        "monitor": {"enabled": False, "mode": "integrated"},
    }}
    config = resolve(settings)
    assert (config.gui.host, config.gui.port, config.open_browser) == ("::1", 29000, False)
    assert config.tensorboard.enabled
    assert not config.monitor.enabled
    config = resolve(settings, ["--host", "127.0.0.2", "--port", "28000",
                                "--disable-tensorboard", "--enable-train-monitor", "--open-browser"])
    assert (config.gui.host, config.gui.port, config.open_browser) == ("127.0.0.2", 28000, True)
    assert not config.tensorboard.enabled
    assert config.monitor.enabled
    assert settings["startup"]["gui"]["port"] == 29000


def test_listen_keeps_monitor_internal_and_probes_effective_hosts():
    calls = []
    config = resolve(argv=["--listen", "--enable-tensorboard"],
                     probe=lambda host, port: calls.append((host, port)) or True)
    assert config.gui.host == config.tensorboard.host == "0.0.0.0"
    assert config.monitor.host == "127.0.0.1"
    assert calls[0] == ("0.0.0.0", 28000)
    assert ("127.0.0.1", 6008) in calls


def test_same_requested_ports_never_reuse_gui():
    config = resolve({"startup": {
        "gui": {"port": 6008},
        "tensorboard": {"enabled": True, "port": 6008},
        "monitor": {"port": 6008},
    }})
    assert config.gui.port == 6008
    assert not config.tensorboard.enabled
    assert config.monitor.port == 6009


def test_fallback_excludes_gui_and_other_auxiliary():
    config = resolve({"startup": {
        "gui": {"port": 6009},
        "tensorboard": {"enabled": True, "port": 6008, "port_conflict": "next_available"},
        "monitor": {"port": 6008},
    }}, probe=lambda host, port: port != 6008)
    assert {config.gui.port, config.monitor.port, config.tensorboard.port} == {6009, 6010, 6011}


def test_gui_conflict_errors_before_auxiliary_probe():
    calls = []
    with pytest.raises(startup.PortConflictError, match="GUI"):
        resolve(probe=lambda host, port: calls.append(port) or False)
    assert calls == [28000]


def test_exhaustion_is_bounded_and_never_returns_occupied_port():
    calls = []
    with pytest.raises(startup.PortConflictError, match="monitor"):
        resolve(probe=lambda host, port: calls.append(port) or port == 28000)
    assert len(calls) == 21


def test_fallback_stops_at_port_limit():
    with pytest.raises(startup.PortConflictError):
        resolve({"startup": {"gui": {"port": 65535, "port_conflict": "next_available"}}},
                probe=lambda host, port: False)


@pytest.mark.parametrize("section,field,value", [
    ("gui", "port", 0), ("gui", "port", True), ("gui", "port_conflict", "disable"),
    ("monitor", "mode", "external"), ("tensorboard", "enabled", "false"),
    ("gui", "open_browser", "false"),
])
def test_invalid_settings_fail_clearly(section, field, value):
    with pytest.raises(ValueError):
        resolve({"startup": {section: {field: value}}})


@pytest.mark.parametrize("host,family", [("127.0.0.1", socket.AF_INET), ("::1", socket.AF_INET6)])
def test_probe_detects_real_occupied_socket(host, family):
    with socket.socket(family, socket.SOCK_STREAM) as listener:
        try:
            listener.bind((host, 0))
        except OSError:
            pytest.skip("Address family unavailable")
        listener.listen()
        port = listener.getsockname()[1]
        assert not startup.port_available(host, port)
    assert startup.port_available(host, port)


def test_saved_gui_cannot_disable_required_gui_listener():
    config = resolve({"startup": {"gui": {"enabled": False, "port": 6008}}})
    assert config.gui.enabled
    assert config.monitor.port != config.gui.port


def test_launch_exports_snapshot_and_does_not_start_disabled_auxiliary():
    settings = {"startup": {
        "gui": {"port": 6008, "open_browser": False},
        "tensorboard": {"enabled": True, "port": 6008},
    }}
    args = gui.parser.parse_args(["--skip-prepare-environment", "--listen"])
    uvicorn = types.SimpleNamespace(run=mock.Mock())
    with mock.patch.object(gui, "args", args, create=True), \
            mock.patch.object(gui, "sanitize_embedded_deps"), \
            mock.patch.object(gui, "train_env_overrides", return_value={}), \
            mock.patch.object(gui, "ensure_requirements_installed"), \
            mock.patch.object(gui, "read_startup_settings", return_value=settings) as read, \
            mock.patch.object(startup, "port_available", return_value=True), \
            mock.patch.object(gui, "run_tensorboard") as tb, \
            mock.patch.object(gui, "run_train_monitor", return_value=None) as monitor, \
            mock.patch("mikazuki.china_hub.enable_china_hub", return_value=False), \
            mock.patch("mikazuki.update_check.local_version", return_value="test"), \
            mock.patch.dict(sys.modules, {"uvicorn": uvicorn}), \
            mock.patch.dict(os.environ, {}, clear=True):
        gui.launch()
        assert os.environ["TRAIN_MONITOR_HOST"] == "127.0.0.1"
        assert os.environ["TRAIN_MONITOR_PORT"] == "6009"
        assert os.environ["MIKAZUKI_PORT"] == "6008"
        assert os.environ["MIKAZUKI_OPEN_BROWSER"] == "0"
        assert os.environ["MIKAZUKI_TENSORBOARD_ENABLED"] == "0"
        assert uvicorn.run.call_args.kwargs["host"] == "0.0.0.0"
        tb.assert_not_called()
        monitor.assert_called_once()
        read.assert_called_once()
    assert settings["startup"]["tensorboard"]["enabled"] is True


def test_gui_conflict_starts_no_children():
    args = gui.parser.parse_args(["--skip-prepare-environment"])
    with mock.patch.object(gui, "args", args, create=True), \
            mock.patch.object(gui, "sanitize_embedded_deps"), \
            mock.patch.object(gui, "train_env_overrides", return_value={}), \
            mock.patch.object(gui, "ensure_requirements_installed"), \
            mock.patch.object(gui, "read_startup_settings", return_value={}), \
            mock.patch.object(startup, "port_available", return_value=False), \
            mock.patch.object(gui, "_popen") as popen, \
            mock.patch("mikazuki.china_hub.enable_china_hub", return_value=False):
        with pytest.raises(startup.PortConflictError):
            gui.launch()
        popen.assert_not_called()


def test_read_missing_settings_does_not_create_user_data(tmp_path):
    from mikazuki.user_data import UserDataStore

    root = tmp_path / "user_data"
    store = UserDataStore(root)
    with mock.patch("mikazuki.user_data.UserDataStore", return_value=store):
        settings = startup.read_startup_settings()
    assert settings == {"schema_version": 1, "revision": 0}
    assert not root.exists()
    assert resolve(settings).gui.port == 28000


def test_gui_fallback_preserves_auxiliary_requested_ports():
    config = resolve({"startup": {
        "gui": {"port": 6007, "port_conflict": "next_available"},
        "monitor": {"port": 6008},
        "tensorboard": {"enabled": True, "port": 6009},
    }}, probe=lambda host, port: port != 6007)
    assert (config.gui.port, config.monitor.port, config.tensorboard.port) == (6010, 6008, 6009)
    assert config.tensorboard.enabled


def test_monitor_fallback_preserves_tensorboard_requested_port():
    config = resolve({"startup": {
        "monitor": {"port": 6008},
        "tensorboard": {"enabled": True, "port": 6009},
    }}, probe=lambda host, port: port != 6008)
    assert (config.monitor.port, config.tensorboard.port) == (6010, 6009)
    assert config.tensorboard.enabled


def test_disabled_auxiliary_does_not_reserve_fallback_port():
    config = resolve({"startup": {
        "monitor": {"port": 6008},
        "tensorboard": {"enabled": False, "port": 6009},
    }}, probe=lambda host, port: port != 6008)
    assert config.monitor.port == 6009


def test_tensorboard_explicit_port_enables_unless_explicitly_disabled():
    settings = {"startup": {"tensorboard": {"enabled": False}}}
    assert resolve(settings, ["--tensorboard-port", "7000"]).tensorboard.enabled
    assert not resolve(settings, ["--tensorboard-port", "7000", "--disable-tensorboard"]).tensorboard.enabled


def test_auxiliary_conflict_warnings_include_requested_and_effective_ports():
    with mock.patch.object(gui.log, "warning") as warning:
        resolve({"startup": {
            "gui": {"port": 6008},
            "monitor": {"port": 6008},
            "tensorboard": {"enabled": True, "port": 6008},
        }})
    messages = "\n".join(str(call.args[0]) for call in warning.call_args_list)
    assert "Train monitor" in messages and "6008" in messages and "6009" in messages
    assert "TensorBoard" in messages and "disabled" in messages


@pytest.mark.parametrize("argv", [[], ["--skip-prepare-environment"]])
def test_bad_config_fails_before_environment_preparation(argv):
    with mock.patch.object(gui, "args", gui.parser.parse_args(argv), create=True), \
            mock.patch.object(gui, "read_startup_settings", side_effect=ValueError("bad config")), \
            mock.patch.object(gui, "sanitize_embedded_deps"), \
            mock.patch.object(gui, "train_env_overrides", return_value={}), \
            mock.patch("mikazuki.china_hub.enable_china_hub", return_value=False), \
            mock.patch.object(gui, "prepare_environment") as prepare, \
            mock.patch.object(gui, "ensure_requirements_installed") as ensure:
        with pytest.raises(ValueError, match="bad config"):
            gui.launch()
        prepare.assert_not_called()
        ensure.assert_not_called()


@pytest.mark.parametrize("host,should_warn", [
    ("0.0.0.0", True), ("::", True), ("192.168.1.10", True),
    ("127.0.0.1", False), ("::1", False), ("localhost", False),
])
def test_outward_listen_auth_warning(host, should_warn):
    with mock.patch.object(gui.log, "warning") as warning:
        resolve(argv=["--host", host])
    messages = "\n".join(str(call.args[0]) for call in warning.call_args_list)
    assert ("authentication" in messages) is should_warn


@pytest.fixture
def browser_startup():
    # Execute the real startup functions without importing training engines/GPU
    # packages. All unrelated startup services are replaced at their boundaries.
    path = Path(gui.__file__).parent / "mikazuki/app/application.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    functions = [node for node in tree.body
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and node.name in {"app_startup", "_start_url"}]
    browser = mock.Mock()
    namespace = {
        "os": os, "sys": types.SimpleNamespace(platform="win32"),
        "webbrowser": browser, "_resolve_browser": lambda: browser,
        "_DEFAULT_START_PAGE": "/lora/sd3.html",
        "app_config": mock.Mock(), "load_schemas": mock.AsyncMock(),
        "load_presets": mock.AsyncMock(), "check_torch_gpu": mock.Mock(),
        "_async_update_check": mock.AsyncMock(),
        "asyncio": types.SimpleNamespace(to_thread=mock.AsyncMock(),
                                        create_task=lambda coro: coro.close()),
        "train_monitor_browser_url": lambda: "http://127.0.0.1:6008/",
        "train_monitor_browser_host": lambda: "127.0.0.1",
        "wait_for_tcp_port": mock.Mock(return_value=True),
    }
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), "exec"), namespace)
    modules = {
        "mikazuki.tasks": types.SimpleNamespace(tm=mock.Mock()),
        "mikazuki.plugin_marketplace.api": types.SimpleNamespace(
            startup_apply_trust_update=mock.Mock(), startup_resume_enabled=mock.Mock()),
    }
    with mock.patch.dict(sys.modules, modules), mock.patch.dict(os.environ, {
        "MIKAZUKI_HOST": "127.0.0.1", "MIKAZUKI_PORT": "28000",
        "TRAIN_MONITOR_ENABLED": "1", "TRAIN_MONITOR_MODE": "integrated",
    }, clear=True):
        yield namespace, browser


@pytest.mark.parametrize("platform,dev,explicit,opens", [
    ("win32", "0", None, True), ("win32", "1", None, False),
    ("linux", "0", None, False), ("win32", "0", "0", False),
    ("linux", "0", "1", True), ("win32", "1", "1", True),
])
def test_browser_policy_and_integrated_monitor_single_tab(browser_startup, platform, dev, explicit, opens):
    namespace, browser = browser_startup
    namespace["sys"].platform = platform
    os.environ["MIKAZUKI_DEV"] = dev
    if explicit is not None:
        os.environ["MIKAZUKI_OPEN_BROWSER"] = explicit
    asyncio.run(namespace["app_startup"]())
    if opens:
        browser.open.assert_called_once_with("http://127.0.0.1:28000/lora/sd3.html")
    else:
        browser.open.assert_not_called()
    namespace["wait_for_tcp_port"].assert_not_called()


@pytest.mark.parametrize("host,browser_host", [
    ("0.0.0.0", "127.0.0.1"), ("::", "[::1]"), ("::1", "[::1]"),
])
def test_browser_url_handles_wildcard_and_ipv6(browser_startup, host, browser_host):
    namespace, _ = browser_startup
    os.environ["MIKAZUKI_HOST"] = host
    assert namespace["_start_url"]() == f"http://{browser_host}:28000/lora/sd3.html"
