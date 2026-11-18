import os
import threading

from mikazuki.engines.kohya.extension_state import (
    FINGERPRINT_SCHEME,
    fingerprint,
    fingerprint_facts,
    read_status,
    write_state,
)
from mikazuki.engines.kohya.settings import Runtime


def make_runtime(tmp_path):
    runtime = Runtime(tmp_path)
    runtime.python.parent.mkdir(parents=True)
    runtime.python.write_text("#!/python\n", encoding="utf-8")
    metadata = runtime.root / ".venv" / "lib" / "torch-2.7.0.dist-info"
    metadata.mkdir(parents=True)
    (metadata / "METADATA").write_text("Name: torch\nVersion: 2.7.0\n", encoding="utf-8")
    return runtime


def successful_audit(runtime):
    return {"ok": True, "errors": [], "versions": {}}


def test_mtime_only_changes_keep_fingerprint(tmp_path):
    runtime = make_runtime(tmp_path)
    before = fingerprint(runtime)
    stat = runtime.python.stat()
    os.utime(runtime.python, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    assert fingerprint(runtime) == before


def test_same_length_content_change_is_detected(tmp_path):
    runtime = make_runtime(tmp_path)
    before = fingerprint(runtime)
    runtime.python.write_text("#!/shell\n", encoding="utf-8")
    assert fingerprint(runtime) != before


def test_legacy_state_audits_and_migrates(tmp_path):
    runtime = make_runtime(tmp_path)
    write_state(runtime, "ready", {"fingerprint": "0" * 64})
    status = read_status(runtime, audit_fn=successful_audit)
    assert status["state"] == "ready"
    assert status["facts"]["fingerprint_scheme"] == FINGERPRINT_SCHEME
    assert runtime.state_file.is_file()


def test_concurrent_legacy_state_migration_audits_once(tmp_path):
    runtime = make_runtime(tmp_path)
    write_state(runtime, "ready", {"fingerprint": "0" * 64})
    barrier = threading.Barrier(2)
    audit_calls = 0

    def counted_audit(rt):
        nonlocal audit_calls
        audit_calls += 1
        return successful_audit(rt)

    results = []

    def worker():
        barrier.wait()
        results.append(read_status(runtime, audit_fn=counted_audit))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert audit_calls == 1
    assert all(result["state"] == "ready" for result in results)
    assert all(result["facts"]["fingerprint_scheme"] == FINGERPRINT_SCHEME for result in results)


def test_legacy_state_with_failed_audit_is_broken(tmp_path):
    runtime = make_runtime(tmp_path)
    write_state(runtime, "ready", {"fingerprint": "0" * 64})
    status = read_status(runtime, audit_fn=lambda rt: {"ok": False, "errors": ["bad runtime"]})
    assert status["state"] == "broken"
    assert "bad runtime" in status["reason"]


def test_current_scheme_mismatch_is_broken(tmp_path):
    runtime = make_runtime(tmp_path)
    write_state(runtime, "ready", {"fingerprint": "0" * 64, "fingerprint_scheme": FINGERPRINT_SCHEME})
    assert read_status(runtime, audit_fn=successful_audit)["state"] == "broken"


def test_missing_state_recovers_complete_environment(tmp_path):
    runtime = make_runtime(tmp_path)
    status = read_status(runtime, audit_fn=successful_audit)
    assert status["state"] == "ready"
    assert status["facts"]["recovery"] == "missing_install_state"
    assert status["facts"]["fingerprint_scheme"] == FINGERPRINT_SCHEME


def test_missing_state_failed_audit_is_broken(tmp_path):
    runtime = make_runtime(tmp_path)
    status = read_status(runtime, audit_fn=lambda rt: {"ok": False, "errors": ["bad runtime"]})
    assert status["state"] == "broken"
    assert "bad runtime" in status["reason"]


def test_install_facts_include_scheme(tmp_path):
    runtime = make_runtime(tmp_path)
    assert fingerprint_facts(runtime)["fingerprint_scheme"] == FINGERPRINT_SCHEME
