"""Exercise the shipped Git helper against real temporary repos; no downloads."""

from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/portable/portable_git.py"
DATA = {
    "sd-models/model.safetensors": b"model\x00weights",
    "train/images/image.png": b"training image",
    "output/lora.safetensors": b"trained weights",
    "logs/run.log": b"training log",
    "toml/autosave/run.toml": b"toml config",
    "config/autosave/run.toml": b"saved config",
    "custom-dataset/image.png": b"untracked user dataset",
}


class PortableGitBehavior(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="portable git tests ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.origin = self.root / "origin.git"
        self.source = self.root / "source"
        self.package = self.root / "Next-Trainer"
        self.env = os.environ.copy()
        self.env.update(
            {
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_AUTHOR_NAME": "Portable test",
                "GIT_AUTHOR_EMAIL": "portable@example.invalid",
                "GIT_COMMITTER_NAME": "Portable test",
                "GIT_COMMITTER_EMAIL": "portable@example.invalid",
            }
        )
        self.run_cmd("git", "init", "--bare", str(self.origin))
        self.run_cmd("git", "clone", self.origin.as_uri(), str(self.source))
        self.git(self.source, "checkout", "-b", "portable-test")
        self.write(self.source, ".gitignore", (ROOT / ".gitignore").read_bytes())
        self.write(self.source, ".gitattributes", b"*.bat text eol=crlf\n")
        self.write(self.source, "gui.py", b"old code\n")
        self.write(self.source, "docs/guide.md", b"old guide\n")
        self.write(self.source, "tests/example.py", b"test file\n")
        self.write(self.source, "scripts/portable/portable_git.py", HELPER.read_bytes())
        self.commit("initial")
        self.helper("seed", source=True)

    def run_cmd(self, *args, ok=True):
        result = subprocess.run(args, env=self.env, capture_output=True)
        if ok:
            self.assertEqual(
                result.returncode, 0, result.stderr.decode(errors="replace")
            )
        return result

    def git(self, root, *args, ok=True):
        return self.run_cmd("git", "-C", str(root), *args, ok=ok).stdout

    def helper(self, action, ok=True, source=False):
        args = [sys.executable, str(HELPER), action, "--trainer-dir", str(self.package)]
        if source:
            args += ["--source", str(self.source)]
        return self.run_cmd(*args, ok=ok)

    def write(self, root, path, data):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def commit(self, message):
        self.git(self.source, "add", "-A")
        self.git(self.source, "commit", "-m", message)
        self.git(self.source, "push", "origin", "HEAD")

    def incoming(self, path="gui.py", data=b"new code\n"):
        self.write(self.source, path, data)
        self.commit("incoming")
        self.git(self.package, "fetch", "origin", "portable-test", "--deepen=50")

    def put_data(self):
        for path, data in DATA.items():
            self.write(self.package, path, data)

    def legacy_bootstrap(self):
        path = "scripts/portable/portable_git.py"
        self.git(self.source, "rm", path)
        self.commit("old version without helper")
        self.package = self.root / "legacy-package"
        self.helper("seed", source=True)
        self.put_data()
        self.write(self.package, "docs/guide.md", b"saved user notes\n")
        self.git(self.package, "stash", "push", "-m", "existing backup")
        self.incoming(path, HELPER.read_bytes())
        self.write(self.package, path, HELPER.read_bytes())
        return path

    def test_first_upgrade_adopts_new_bootstrap_file(self):
        path = self.legacy_bootstrap()
        before = self.git(self.package, "stash", "list")
        self.helper("update")
        self.assert_data()
        self.assertEqual(self.git(self.package, "stash", "list"), before)
        self.assertEqual(
            self.git(self.package, "status", "--porcelain", "--untracked-files=no"), b""
        )
        self.assertEqual((self.package / path).read_bytes(), HELPER.read_bytes())

    def test_new_bootstrap_with_different_content_is_not_overwritten(self):
        path = self.legacy_bootstrap()
        self.write(self.package, path, b"user-owned content\n")
        before = self.git(self.package, "ls-files", "--stage")
        self.assertNotEqual(self.helper("update", ok=False).returncode, 0)
        self.assertEqual((self.package / path).read_bytes(), b"user-owned content\n")
        self.assertEqual(self.git(self.package, "ls-files", "--stage"), before)
        self.assert_data()

    def test_failed_first_upgrade_restores_index_and_keeps_download(self):
        path = self.legacy_bootstrap()
        self.incoming("gui.py", b"incoming code\n")
        self.write(self.package, "gui.py", b"user edit\n")
        before = self.git(self.package, "ls-files", "--stage")
        stash = self.git(self.package, "stash", "list")
        self.assertNotEqual(self.helper("update", ok=False).returncode, 0)
        self.assertEqual(self.git(self.package, "ls-files", "--stage"), before)
        self.assertEqual(self.git(self.package, "stash", "list"), stash)
        self.assertEqual((self.package / path).read_bytes(), HELPER.read_bytes())
        self.assertEqual((self.package / "gui.py").read_bytes(), b"user edit\n")
        self.assert_data()

    def assert_data(self):
        for path, data in DATA.items():
            self.assertEqual((self.package / path).read_bytes(), data, path)

    def test_cropped_crlf_blob_updates_without_false_local_changes(self):
        path = "build-scripts/legacy.ps1"
        self.write(self.source, path, b"Write-Host old\r\n")
        # Commit the historical blob before attributes began normalizing it.
        self.commit("legacy CRLF blob")
        self.write(self.source, ".gitattributes", b"*.ps1 text eol=crlf\n")
        self.git(self.source, "add", ".gitattributes")
        self.git(self.source, "commit", "-m", "enable text normalization")
        self.git(self.source, "push", "origin", "HEAD")
        self.package = self.root / "legacy-crlf-package"
        self.run_cmd(
            "git",
            "clone",
            "--branch",
            "portable-test",
            self.origin.as_uri(),
            str(self.package),
        )
        (self.package / path).unlink()
        (self.package / "docs/guide.md").unlink()
        (self.package / "tests/example.py").unlink()
        self.put_data()
        self.git(self.source, "rm", "tests/example.py")
        self.incoming(path, b"Write-Host new\n")
        self.helper("update")
        self.assert_data()
        self.assertEqual(
            (self.package / path).read_bytes().replace(b"\r\n", b"\n"),
            b"Write-Host new\n",
        )
        self.assertEqual((self.package / "docs/guide.md").read_bytes(), b"old guide\n")
        self.assertFalse((self.package / "tests/example.py").exists())
        self.assertEqual(
            self.git(self.package, "status", "--porcelain", "--untracked-files=no"), b""
        )

    def test_failed_update_does_not_restore_missing_old_files(self):
        (self.package / "docs/guide.md").unlink()
        self.incoming()
        self.write(self.package, "gui.py", b"user changes\n")
        before = self.git(self.package, "ls-files", "--stage")
        self.assertNotEqual(self.helper("update", ok=False).returncode, 0)
        self.assertFalse((self.package / "docs/guide.md").exists())
        self.assertEqual(self.git(self.package, "ls-files", "--stage"), before)

    def test_real_v300_cropped_package_upgrade(self):
        if self.run_cmd(
            "git", "-C", str(ROOT), "rev-parse", "--verify", "v3.0.0^{commit}", ok=False
        ).returncode:
            self.skipTest("v3.0.0 history unavailable in shallow release checkout")
        self.package = self.root / "v300-package"
        self.run_cmd(
            "git", "clone", "--shared", "--no-checkout", str(ROOT), str(self.package)
        )
        self.git(self.package, "checkout", "-b", "legacy", "v3.0.0")
        keep_dirs = {
            "assets",
            "mikazuki",
            "frontend",
            "config",
            "scripts",
            "vendor",
            "train_monitor",
        }
        keep_files = {
            "gui.py",
            "run_gui.bat",
            "requirements.txt",
            "setup_environment.py",
            "VERSION",
            "LICENSE",
            "NOTICE.md",
            "CHANGELOG.md",
            "README.md",
            "README-zh.md",
        }
        for raw in self.git(self.package, "ls-files", "-z").split(b"\0"):
            if not raw:
                continue
            path = Path(os.fsdecode(raw))
            full = self.package / path
            if (
                path.parts[0] not in keep_dirs
                and str(path) not in keep_files
                and (full.is_file() or full.is_symlink())
            ):
                full.unlink()
        # Emulate the real bootstrap manifest, including its source/destination mapping.
        manifest = (ROOT / "scripts/portable/portable_updater_common.ps1").read_text(
            encoding="utf-8-sig"
        )
        for source, destination in re.findall(
            r'Src = "([^"]+)"; Dest = "Next-Trainer/([^"]+)"', manifest
        ):
            payload = self.git(ROOT, "show", f"HEAD:{source}")
            self.write(self.package, destination, payload)
        self.put_data()
        self.git(self.package, "fetch", str(ROOT), "HEAD")
        self.helper("update")
        self.assertEqual(
            self.git(self.package, "rev-parse", "HEAD"),
            self.git(ROOT, "rev-parse", "HEAD"),
        )
        self.assert_data()
        self.assertEqual(self.git(self.package, "stash", "list"), b"")
        # Raw bootstrap downloads can use LF while checkout requests CRLF.
        # Compare content with HEAD rather than working-EOL/stat hints.
        self.git(self.package, "diff", "--exit-code", "HEAD")

    def test_seed_is_complete_clean_shallow_checkout(self):
        self.assertTrue((self.package / "docs/guide.md").is_file())
        self.assertTrue((self.package / "tests/example.py").is_file())
        self.assertEqual(self.git(self.package, "status", "--porcelain"), b"")
        self.assertEqual(
            self.git(self.package, "rev-parse", "--is-shallow-repository").strip(),
            b"true",
        )
        self.helper("verify")

    def test_update_preserves_ignored_and_untracked_data(self):
        self.put_data()
        self.incoming()
        self.helper("update")
        self.assert_data()
        self.assertEqual((self.package / "gui.py").read_bytes(), b"new code\n")
        self.assertEqual(self.git(self.package, "stash", "list"), b"")

    def test_missing_ignore_does_not_collect_user_data(self):
        (self.package / ".gitignore").unlink()
        self.put_data()
        self.incoming()
        self.helper("update")
        self.assert_data()
        self.assertEqual(self.git(self.package, "stash", "list"), b"")

    def test_update_accepts_lf_worktree_with_crlf_checkout_rules(self):
        path = "frontend/page.vue"
        self.write(self.source, ".gitattributes", b"*.vue text eol=crlf\n")
        self.incoming(path, b"old page\n")
        self.helper("update")
        self.incoming(path, b"new page\n")
        self.write(self.package, path, b"old page\n")
        self.helper("update")
        self.assertEqual((self.package / path).read_bytes(), b"new page\r\n")

    def assert_conflict_preserved(self, path):
        self.put_data()
        self.write(self.package, "gui.py", b"saved old edit\n")
        self.git(self.package, "stash", "push", "-m", "existing user stash")
        self.git(self.package, "config", "merge.autostash", "true")
        self.write(self.package, path, b"user data\n")
        self.write(self.source, path, b"incoming conflicting data\n")
        self.git(self.source, "add", "--force", "--", path)
        self.commit("conflict")
        self.git(self.package, "fetch", "origin", "portable-test", "--deepen=50")
        before = {
            name: self.git(self.package, *cmd)
            for name, cmd in {
                "head": ("rev-parse", "HEAD"),
                "index": ("ls-files", "--stage"),
                "stash": ("stash", "list"),
            }.items()
        }
        self.assertNotEqual(self.helper("update", ok=False).returncode, 0)
        self.assertEqual((self.package / path).read_bytes(), b"user data\n")
        self.assertEqual(self.git(self.package, "rev-parse", "HEAD"), before["head"])
        self.assertEqual(self.git(self.package, "ls-files", "--stage"), before["index"])
        self.assertEqual(self.git(self.package, "stash", "list"), before["stash"])

    def test_tracked_conflict_preserves_user_edits_and_stash(self):
        self.assert_conflict_preserved("gui.py")

    def test_untracked_conflict_preserves_user_data_and_stash(self):
        self.assert_conflict_preserved("custom-dataset/image.png")

    def test_ignored_conflict_preserves_user_data_and_stash(self):
        self.assert_conflict_preserved("sd-models/model.safetensors")

    def test_ignored_directory_blocking_incoming_file_is_preserved(self):
        self.write(self.package, "output/result/private.bin", b"private output")
        self.write(self.source, "output/result", b"incoming file")
        self.git(self.source, "add", "--force", "output/result")
        self.commit("file directory collision")
        self.git(self.package, "fetch", "origin", "portable-test", "--deepen=50")
        self.assertNotEqual(self.helper("update", ok=False).returncode, 0)
        self.assertEqual(
            (self.package / "output/result/private.bin").read_bytes(), b"private output"
        )

    def test_old_cropped_package_is_repaired_and_updated_without_stashing(self):
        self.put_data()
        (self.package / "docs/guide.md").unlink()
        self.incoming("docs/guide.md", b"changed guide\n")
        self.helper("update")
        self.assert_data()
        self.assertEqual(
            (self.package / "docs/guide.md").read_bytes(), b"changed guide\n"
        )
        self.assertEqual(self.git(self.package, "stash", "list"), b"")

    def test_bootstrap_file_already_matching_incoming_is_allowed(self):
        path = "scripts/portable/portable_git.py"
        content = HELPER.read_bytes() + b"\n# updater revision\n"
        self.incoming(path, content)
        self.write(self.package, path, content)
        self.helper("update")
        self.assertEqual(self.git(self.package, "status", "--porcelain"), b"")

    def test_bootstrap_staging_is_undone_when_merge_fails(self):
        path = "scripts/portable/portable_git.py"
        content = HELPER.read_bytes() + b"\n# bootstrap revision\n"
        self.write(self.source, path, content)
        self.incoming()
        self.write(self.package, path, content)
        self.write(self.package, "gui.py", b"user edit\n")
        before = self.git(self.package, "ls-files", "--stage")
        self.assertNotEqual(self.helper("update", ok=False).returncode, 0)
        self.assertEqual(self.git(self.package, "ls-files", "--stage"), before)
        self.assertEqual((self.package / path).read_bytes(), content)
        self.assertEqual((self.package / "gui.py").read_bytes(), b"user edit\n")

    def test_bootstrap_batch_upgrade_with_existing_text_attributes(self):
        path, content = self.prepare_bootstrap_attributes_upgrade()
        self.helper("update")
        self.assertEqual((self.package / path).read_bytes(), content)
        self.assertEqual(self.git(self.package, "diff", "HEAD", "--name-only"), b"")

    def prepare_bootstrap_attributes_upgrade(self):
        path = "scripts/portable/templates/Update-Next-Trainer.bat"
        self.incoming(path, b"@echo off\necho old\n")
        self.helper("update")
        self.write(
            self.source, ".gitattributes",
            b"*.bat text eol=crlf\n" + path.encode() + b" -text\n",
        )
        content = b"@echo off\r\necho new\r\n"
        self.incoming(path, content)
        self.write(self.package, path, content)
        return path, content

    def test_failed_bootstrap_upgrade_restores_attributes_and_index(self):
        path, content = self.prepare_bootstrap_attributes_upgrade()
        self.incoming()
        self.write(self.package, "gui.py", b"user edit\n")
        attributes = (self.package / ".gitattributes").read_bytes()
        index = self.git(self.package, "ls-files", "--stage")
        self.assertNotEqual(self.helper("update", ok=False).returncode, 0)
        self.assertEqual((self.package / ".gitattributes").read_bytes(), attributes)
        self.assertEqual(self.git(self.package, "ls-files", "--stage"), index)
        self.assertEqual((self.package / path).read_bytes(), content)
        self.assertEqual((self.package / "gui.py").read_bytes(), b"user edit\n")

    def test_bootstrap_upgrade_preserves_user_attributes(self):
        self.prepare_bootstrap_attributes_upgrade()
        attributes = b"*.bat text eol=crlf\n# user setting\n"
        self.write(self.package, ".gitattributes", attributes)
        self.assertNotEqual(self.helper("update", ok=False).returncode, 0)
        self.assertEqual((self.package / ".gitattributes").read_bytes(), attributes)

    def test_missing_program_path_blocked_by_user_file_is_preserved(self):
        (self.package / "docs/guide.md").unlink()
        (self.package / "docs").rmdir()
        self.write(self.package, "docs", b"user document")
        self.incoming()
        self.assertNotEqual(self.helper("update", ok=False).returncode, 0)
        self.assertEqual((self.package / "docs").read_bytes(), b"user document")

    def test_success_preserves_existing_stash_and_unrelated_edit(self):
        self.write(self.package, "gui.py", b"saved edit\n")
        self.git(self.package, "stash", "push", "-m", "user backup")
        before = self.git(self.package, "stash", "list")
        self.write(self.package, "docs/guide.md", b"user notes\n")
        self.incoming()
        self.helper("update")
        self.assertEqual(self.git(self.package, "stash", "list"), before)
        self.assertEqual((self.package / "docs/guide.md").read_bytes(), b"user notes\n")

    def test_no_successful_fetch_leaves_data_untouched(self):
        self.put_data()
        self.assertNotEqual(self.helper("update", ok=False).returncode, 0)
        self.assert_data()

    @unittest.skipUnless(os.name == "nt", "requires Windows cmd.exe")
    def test_windows_batch_entrypoint_updates_with_user_data(self):
        self.assert_windows_batch_update()

    @unittest.skipUnless(os.name == "nt", "requires Windows cmd.exe")
    def test_windows_batch_entrypoint_updates_full_checkout(self):
        self.git(self.package, "fetch", "origin", "--unshallow")
        self.assertEqual(
            self.git(self.package, "rev-parse", "--is-shallow-repository").strip(),
            b"false",
        )
        self.assert_windows_batch_update()

    @unittest.skipUnless(os.name == "nt", "requires Windows cmd.exe")
    def test_windows_batch_entrypoint_from_raw_git_blob(self):
        self.assert_windows_batch_update(raw_download=True)

    def assert_windows_batch_update(self, raw_download=False):
        self.put_data()
        self.write(self.source, "gui.py", b"batch update\n")
        self.commit("batch update")
        launcher = self.root / "Update-Next-Trainer.bat"
        path = "build-scripts/templates/Update-Next-Trainer.bat"
        payload = (
            self.git(ROOT, "show", f"HEAD:{path}")
            if raw_download else (ROOT / path).read_bytes()
        )
        launcher.write_bytes(payload)
        self.run_cmd(
            "cmd",
            "/c",
            "mklink",
            "/J",
            str(self.root / "python_embeded"),
            sys.base_prefix,
        )
        result = subprocess.run(
            ["cmd", "/c", str(launcher), "--no-bootstrap"],
            env=self.env,
            input=b"\n",
            capture_output=True,
            timeout=60,
        )
        self.assertEqual(
            result.returncode,
            0,
            (result.stdout + result.stderr).decode(errors="replace"),
        )
        self.assert_data()
        self.assertEqual((self.package / "gui.py").read_bytes(), b"batch update\n")
        self.assertEqual(self.git(self.package, "stash", "list"), b"")

    def test_mirror_fetch_uses_fetch_head_not_stale_origin(self):
        old = self.git(self.package, "rev-parse", "origin/portable-test")
        self.write(self.source, "gui.py", b"mirror update\n")
        self.commit("mirror")
        self.git(
            self.package, "fetch", self.origin.as_uri(), "portable-test", "--deepen=50"
        )
        self.assertEqual(
            self.git(self.package, "rev-parse", "origin/portable-test"), old
        )
        self.helper("update")
        self.assertEqual((self.package / "gui.py").read_bytes(), b"mirror update\n")

    def test_diverged_history_stops_without_touching_data(self):
        self.put_data()
        self.write(self.package, "local.txt", b"local commit")
        self.git(self.package, "add", "local.txt")
        self.git(self.package, "commit", "-m", "local")
        self.incoming()
        before = self.git(self.package, "rev-parse", "HEAD")
        self.assertNotEqual(self.helper("update", ok=False).returncode, 0)
        self.assertEqual(self.git(self.package, "rev-parse", "HEAD"), before)
        self.assert_data()

    def test_verifier_rejects_missing_tracked_files_and_ignore_rules(self):
        (self.package / "docs/guide.md").unlink()
        self.assertNotEqual(self.helper("verify", ok=False).returncode, 0)
        self.git(self.package, "restore", "docs/guide.md")
        (self.package / ".gitignore").unlink()
        self.assertNotEqual(self.helper("verify", ok=False).returncode, 0)
        self.write(self.package, ".gitignore", b"# no protection\n")
        self.git(self.package, "add", ".gitignore")
        self.git(self.package, "commit", "-m", "bad rules")
        self.assertNotEqual(self.helper("verify", ok=False).returncode, 0)

    def test_seed_refuses_existing_destination(self):
        self.put_data()
        self.assertNotEqual(self.helper("seed", source=True, ok=False).returncode, 0)
        self.assert_data()

    def test_seed_uses_upstream_branch_for_build_worktree(self):
        original_source = self.source
        worktree = self.root / "build-worktree"
        self.git(
            self.source,
            "worktree",
            "add",
            "-b",
            "temporary-build",
            "--track",
            str(worktree),
            "origin/portable-test",
        )
        self.source = worktree
        self.package = self.root / "second-package"
        self.helper("seed", source=True)
        self.assertEqual(
            self.git(self.package, "branch", "--show-current").strip(), b"portable-test"
        )
        self.source = original_source
        self.write(self.source, "gui.py", b"next published version\n")
        self.commit("publish next version")
        self.git(self.package, "fetch", "origin", "--deepen=50")
        self.helper("update")
        self.assertEqual(
            (self.package / "gui.py").read_bytes(), b"next published version\n"
        )

    def test_seed_rejects_uncommitted_source(self):
        self.package = self.root / "second-package"
        self.write(self.source, "gui.py", b"uncommitted code")
        self.assertNotEqual(self.helper("seed", source=True, ok=False).returncode, 0)
        self.assertFalse(self.package.exists())

    def test_seed_builds_committed_local_changes_without_remote_access(self):
        self.package = self.root / "second-package"
        self.write(self.source, "gui.py", b"unpublished code")
        self.git(self.source, "add", "gui.py")
        self.git(self.source, "commit", "-m", "unpublished")
        self.git(
            self.source,
            "remote",
            "set-url",
            "origin",
            "https://example.invalid/offline.git",
        )
        self.helper("seed", source=True)
        self.assertEqual(
            self.git(self.package, "rev-parse", "HEAD"),
            self.git(self.source, "rev-parse", "HEAD"),
        )
        self.assertEqual((self.package / "gui.py").read_bytes(), b"unpublished code")
        self.assertEqual(
            self.git(self.package, "remote", "get-url", "origin").strip(),
            b"https://example.invalid/offline.git",
        )


if __name__ == "__main__":
    unittest.main()
