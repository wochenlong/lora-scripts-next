"""mikazuki/cloud_mode.py 单测：环境变量解析与安装/卸载门禁。"""
from __future__ import annotations

import unittest

from mikazuki.cloud_mode import current, install_block_reason, uninstall_block_reason


class CurrentTests(unittest.TestCase):
    def test_default_off(self):
        self.assertEqual(current({}), {"cloud_mode": False, "engine": None})

    def test_active_with_engine(self):
        env = {"NEXT_TRAINER_CLOUD": "1", "NEXT_TRAINER_CLOUD_ENGINE": "musubi"}
        self.assertEqual(current(env), {"cloud_mode": True, "engine": "musubi"})

    def test_engine_ignored_when_off(self):
        env = {"NEXT_TRAINER_CLOUD": "0", "NEXT_TRAINER_CLOUD_ENGINE": "musubi"}
        self.assertEqual(current(env), {"cloud_mode": False, "engine": None})


class GuardTests(unittest.TestCase):
    ENV = {"NEXT_TRAINER_CLOUD": "1", "NEXT_TRAINER_CLOUD_ENGINE": "musubi"}

    def test_off_mode_never_blocks(self):
        self.assertIsNone(install_block_reason("kohya", {}))
        self.assertIsNone(uninstall_block_reason("kohya", {}))

    def test_other_engine_install_blocked(self):
        reason = install_block_reason("kohya", self.ENV)
        self.assertIsNotNone(reason)
        self.assertIn("musubi", reason)

    def test_locked_engine_install_allowed(self):
        self.assertIsNone(install_block_reason("musubi", self.ENV))

    def test_uninstall_always_blocked_in_cloud(self):
        self.assertIsNotNone(uninstall_block_reason("musubi", self.ENV))
        self.assertIsNotNone(uninstall_block_reason("kohya", self.ENV))


if __name__ == "__main__":
    unittest.main()
