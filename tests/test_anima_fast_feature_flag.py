from __future__ import annotations

import asyncio
import json
import os
import unittest

from starlette.requests import Request

from mikazuki.app import api


def make_request(payload: dict) -> Request:
    body = json.dumps(payload).encode("utf-8")

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({"type": "http", "method": "POST", "path": "/api/run", "headers": []}, receive)


class AnimaFastFeatureFlagTests(unittest.TestCase):
    def setUp(self):
        self.previous = os.environ.pop("LORA_ENABLE_ANIMA_FAST", None)

    def tearDown(self):
        if self.previous is None:
            os.environ.pop("LORA_ENABLE_ANIMA_FAST", None)
        else:
            os.environ["LORA_ENABLE_ANIMA_FAST"] = self.previous
        asyncio.run(api.load_schemas())

    def test_schema_is_hidden_when_feature_flag_is_disabled(self):
        asyncio.run(api.load_schemas())

        names = {schema["name"] for schema in api.avaliable_schemas}

        self.assertNotIn("anima-lora-fast", names)

    def test_schema_is_visible_when_feature_flag_is_enabled(self):
        os.environ["LORA_ENABLE_ANIMA_FAST"] = "1"

        asyncio.run(api.load_schemas())

        names = {schema["name"] for schema in api.avaliable_schemas}
        self.assertIn("anima-lora-fast", names)

    def test_shared_schema_is_loaded_before_anima_fast_schema(self):
        os.environ["LORA_ENABLE_ANIMA_FAST"] = "1"

        asyncio.run(api.load_schemas())

        names = [schema["name"] for schema in api.avaliable_schemas]
        self.assertLess(names.index("shared"), names.index("anima-lora-fast"))

    def test_run_rejects_anima_fast_when_feature_flag_is_disabled(self):
        response = asyncio.run(api.create_toml_file(make_request({"model_train_type": "anima-lora-fast"})))

        self.assertEqual(response.status, "fail")
        self.assertIn("disabled", response.message)


if __name__ == "__main__":
    unittest.main()
