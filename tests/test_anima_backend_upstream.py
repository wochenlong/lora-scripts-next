import os
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mikazuki.anima_backend.upstream import (
    _is_initialized_git_checkout,
    pinned_commit,
    prefer_upstream_imports,
    resolve_upstream_path,
    upstream_entrypoint,
    verify_pinned_commit,
)


class AnimaBackendUpstreamTests(unittest.TestCase):
    def test_resolve_upstream_path_from_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "repo"
            upstream = root / "vendor" / "sd-scripts"
            upstream.mkdir(parents=True)
            config = root / "config" / "anima_backend.toml"
            config.parent.mkdir()
            config.write_text(
                '[backend]\nupstream_path = "vendor/sd-scripts"\nentrypoint = "anima_train_network.py"\n',
                encoding="utf-8",
            )

            self.assertEqual(resolve_upstream_path(root, config), upstream.resolve())

    def test_upstream_entrypoint_uses_configured_script(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            upstream = Path(temp_dir) / "vendor" / "sd-scripts"
            upstream.mkdir(parents=True)
            script = upstream / "anima_train_network.py"
            script.write_text("", encoding="utf-8")

            self.assertEqual(upstream_entrypoint(upstream, "anima_train_network.py"), script)

    def test_upstream_entrypoint_fails_when_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            upstream = Path(temp_dir)

            with self.assertRaises(FileNotFoundError):
                upstream_entrypoint(upstream, "anima_train_network.py")

    def test_prefer_upstream_imports_places_path_first(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            upstream = Path(temp_dir).resolve()
            original = list(sys.path)
            try:
                prefer_upstream_imports(upstream)

                self.assertEqual(sys.path[0], str(upstream))
                self.assertEqual(sys.path.count(str(upstream)), 1)
            finally:
                sys.path[:] = original

    def test_verify_pinned_commit_matches_submodule_head(self):
        root = Path.cwd()

        self.assertEqual(
            verify_pinned_commit(root),
            pinned_commit(root),
        )

    def _git(self, cwd: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(cwd),
             "-c", "user.email=t@t", "-c", "user.name=t",
             *args],
            check=True, capture_output=True, text=True,
        )

    def _init_repo_with_commit(self, path: Path, filename: str, message: str) -> None:
        subprocess.run(["git", "init", "-q", str(path)], check=True)
        (path / filename).write_text("seed", encoding="utf-8")
        self._git(path, "add", filename)
        self._git(path, "commit", "-q", "-m", message)

    def _make_fake_repo(self, temp_dir: str, pinned: str, upstream_initialized: bool):
        root = Path(temp_dir) / "repo"
        upstream = root / "vendor" / "sd-scripts"
        upstream.mkdir(parents=True)
        config = root / "config" / "anima_backend.toml"
        config.parent.mkdir()
        config.write_text(
            "[backend]\n"
            'upstream_path = "vendor/sd-scripts"\n'
            'entrypoint = "anima_train_network.py"\n'
            f'pinned_commit = "{pinned}"\n',
            encoding="utf-8",
        )
        # Make the parent ``root`` look like a git repo so rev-parse would
        # otherwise leak the superproject HEAD into the upstream check.
        self._init_repo_with_commit(root, "seed.txt", "seed")
        if upstream_initialized:
            self._init_repo_with_commit(upstream, "file.txt", "init")
        return root, upstream

    def test_is_initialized_git_checkout_false_for_empty_submodule(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _, upstream = self._make_fake_repo(temp_dir, "deadbeef", upstream_initialized=False)
            self.assertFalse(_is_initialized_git_checkout(upstream))

    def test_is_initialized_git_checkout_true_for_real_repo(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _, upstream = self._make_fake_repo(temp_dir, "deadbeef", upstream_initialized=True)
            self.assertTrue(_is_initialized_git_checkout(upstream))

    def test_verify_pinned_commit_raises_for_uninitialized_submodule(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root, upstream = self._make_fake_repo(temp_dir, "deadbeef", upstream_initialized=False)
            with mock.patch.dict(os.environ, {"ANIMA_STRICT_COMMIT": "1", "ANIMA_ALLOW_COMMIT_DRIFT": ""}):
                with self.assertRaises(RuntimeError) as ctx:
                    verify_pinned_commit(root)
            self.assertIn("git submodule update --init", str(ctx.exception))
            self.assertIn(str(upstream), str(ctx.exception))

    def test_current_upstream_commit_raises_for_uninitialized_submodule(self):
        from mikazuki.anima_backend.upstream import current_upstream_commit

        with tempfile.TemporaryDirectory() as temp_dir:
            _, upstream = self._make_fake_repo(temp_dir, "deadbeef", upstream_initialized=False)
            with self.assertRaises(RuntimeError) as ctx:
                current_upstream_commit(upstream)
            self.assertIn("git submodule update --init", str(ctx.exception))

    def test_verify_pinned_commit_raises_on_commit_drift(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root, _ = self._make_fake_repo(temp_dir, "deadbeef", upstream_initialized=True)
            with mock.patch.dict(os.environ, {"ANIMA_STRICT_COMMIT": "1", "ANIMA_ALLOW_COMMIT_DRIFT": ""}):
                with self.assertRaises(RuntimeError) as ctx:
                    verify_pinned_commit(root)
            self.assertIn("commit mismatch", str(ctx.exception))

    def test_verify_pinned_commit_drift_allowed_via_env(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root, upstream = self._make_fake_repo(temp_dir, "deadbeef", upstream_initialized=True)
            actual_head = subprocess.run(
                ["git", "-C", str(upstream), "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            with mock.patch.dict(os.environ, {"ANIMA_ALLOW_COMMIT_DRIFT": "1"}):
                self.assertEqual(verify_pinned_commit(root), actual_head)

    def test_verify_pinned_commit_skips_auto_init_when_env_set(self):
        from mikazuki.anima_backend import upstream as upstream_mod

        with tempfile.TemporaryDirectory() as temp_dir:
            root, _ = self._make_fake_repo(temp_dir, "deadbeef", upstream_initialized=False)
            with mock.patch.dict(os.environ, {"ANIMA_SKIP_AUTO_INIT": "1"}), \
                    mock.patch.object(upstream_mod.subprocess, "run") as run_mock:
                with self.assertRaises(RuntimeError):
                    verify_pinned_commit(root)
                # No git submodule update --init should have been attempted.
                for call in run_mock.call_args_list:
                    args = call.args[0] if call.args else []
                    self.assertNotIn("submodule", args)

    def test_verify_pinned_commit_attempts_auto_init(self):
        from mikazuki.anima_backend import upstream as upstream_mod

        with tempfile.TemporaryDirectory() as temp_dir:
            root, upstream = self._make_fake_repo(temp_dir, "deadbeef", upstream_initialized=False)

            # Simulate a successful submodule update by initializing the
            # upstream as a real git repo when the auto-init command runs.
            real_run = upstream_mod.subprocess.run

            def fake_run(cmd, *args, **kwargs):
                if isinstance(cmd, list) and len(cmd) >= 4 and cmd[3] == "submodule":
                    self._init_repo_with_commit(upstream, "file.txt", "init")
                    return subprocess.CompletedProcess(cmd, 0, "", "")
                return real_run(cmd, *args, **kwargs)

            with mock.patch.object(upstream_mod.subprocess, "run", side_effect=fake_run), \
                    mock.patch.dict(os.environ, {"ANIMA_STRICT_COMMIT": "1", "ANIMA_ALLOW_COMMIT_DRIFT": ""}):
                # Drift is expected (pinned != actual) but auto-init must have
                # run before the drift check kicks in.
                with self.assertRaises(RuntimeError) as ctx:
                    verify_pinned_commit(root)
                self.assertIn("commit mismatch", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
