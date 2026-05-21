import unittest
from unittest import mock

from mikazuki import portable_utils


class PortableFlashAttentionTests(unittest.TestCase):
    def test_flash_attn_wheel_url_uses_python_tag_and_region(self):
        url = portable_utils.flash_attn_wheel_url("china", "cp310")

        self.assertIn("hf-mirror.com", url)
        self.assertTrue(url.endswith("-cp310-cp310-win_amd64.whl"))
        self.assertIn("cu128torch2.7.0", url)

    def test_sanitize_embedded_deps_keeps_usable_stack(self):
        with (
            mock.patch.object(portable_utils, "is_embedded_python", return_value=True),
            mock.patch.object(portable_utils.importlib.util, "find_spec", return_value=object()),
            mock.patch.object(portable_utils, "flash_attn_probe", return_value=(True, "ok")),
            mock.patch.object(portable_utils.subprocess, "run") as run,
        ):
            portable_utils.sanitize_embedded_deps()

        run.assert_not_called()

    def test_sanitize_embedded_deps_removes_broken_stack(self):
        with (
            mock.patch.object(portable_utils, "is_embedded_python", return_value=True),
            mock.patch.object(portable_utils.importlib.util, "find_spec", return_value=object()),
            mock.patch.object(portable_utils, "flash_attn_probe", return_value=(False, "missing triton")),
            mock.patch.object(portable_utils.subprocess, "run") as run,
        ):
            portable_utils.sanitize_embedded_deps()

        run.assert_called_once()
        args = run.call_args.args[0]
        self.assertIn("uninstall", args)
        self.assertIn("flash-attn", args)
        self.assertIn("triton-windows", args)

    def test_train_env_overrides_do_not_disable_working_flash_stack(self):
        with (
            mock.patch.object(portable_utils, "is_embedded_python", return_value=True),
            mock.patch.object(portable_utils, "flash_attn_stack_usable", return_value=True),
        ):
            self.assertEqual(portable_utils.train_env_overrides(), {})

    def test_train_env_overrides_fallback_to_sdpa_when_broken(self):
        with (
            mock.patch.object(portable_utils, "is_embedded_python", return_value=True),
            mock.patch.object(portable_utils, "flash_attn_stack_usable", return_value=False),
        ):
            self.assertEqual(
                portable_utils.train_env_overrides(),
                {"TRANSFORMERS_ATTN_IMPLEMENTATION": "sdpa"},
            )


if __name__ == "__main__":
    unittest.main()
