import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from mikazuki.tagger import cli
from mikazuki.tagger import local_models
from mikazuki.tagger import service
from mikazuki.tagger.cli import resolve_api_key


class FakeInterrogator:
    def __init__(self):
        self.calls = 0
        self.unloaded = False

    def interrogate(self, image):
        self.calls += 1
        return {
            "rating": [("general", 0.9)],
            "general": [("blue_hair", 0.8), ("lowres", 0.7), ("red_eyes", 0.2)],
            "character": [("test_character", 0.7)],
            "model": [],
        }

    def unload(self):
        self.unloaded = True
        return True


class FakeResponse:
    def __init__(self, data, status_code=200):
        self.data = data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.data


class FakeHttpClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return self.response


class TaggerServiceTests(unittest.TestCase):
    def make_image(self, path: Path):
        Image.new("RGB", (8, 8), color=(255, 0, 0)).save(path)

    def test_collect_image_paths_supports_folder_glob_recursive_and_skips_non_images(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.make_image(root / "a.png")
            (root / "note.txt").write_text("not an image", encoding="utf-8")
            child = root / "child"
            child.mkdir()
            self.make_image(child / "b.jpg")

            self.assertEqual([p.name for p in service.collect_image_paths(str(root))], ["a.png"])
            self.assertEqual(
                [p.name for p in service.collect_image_paths(str(root / "*.png"))],
                ["a.png"],
            )
            self.assertEqual(
                [p.name for p in service.collect_image_paths(str(root), recursive=True)],
                ["a.png", "b.jpg"],
            )

    def test_local_tagger_applies_thresholds_tag_edits_dedupe_and_conflict(self):
        fake = FakeInterrogator()
        original = service.available_interrogators.get("fake")
        service.available_interrogators["fake"] = fake
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                image_path = root / "a.png"
                self.make_image(image_path)
                image_path.with_suffix(".txt").write_text("old_tag", encoding="utf-8")

                skipped = service.run_local_tagger(str(root), model="fake", on_conflict="ignore")
                self.assertEqual(skipped.skipped, 1)
                self.assertEqual(fake.calls, 0)

                result = service.run_local_tagger(
                    str(root),
                    model="fake",
                    threshold=0.35,
                    character_threshold=0.6,
                    additional_tags="blue hair, best quality",
                    exclude_tags="lowres",
                    on_conflict="copy",
                    replace_underscore=True,
                    escape_tag=False,
                )

                self.assertEqual(result.processed, 1)
                self.assertEqual(
                    image_path.with_suffix(".txt").read_text(encoding="utf-8"),
                    "blue hair, best quality, test character",
                )
                self.assertTrue(fake.unloaded)
        finally:
            if original is None:
                del service.available_interrogators["fake"]
            else:
                service.available_interrogators["fake"] = original

    def test_openai_client_posts_expected_chat_completions_payload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "a.png"
            self.make_image(image_path)
            http_client = FakeHttpClient(
                FakeResponse({"choices": [{"message": {"content": "a concise caption"}}]})
            )
            client = service.OpenAICompatibleCaptionClient(
                endpoint="https://example.test/v1/",
                api_key="secret",
                model="vision-model",
                prompt="caption it",
                retries=0,
                http_client=http_client,
            )

            caption = client.caption(image_path)

            self.assertEqual(caption, "a concise caption")
            call = http_client.calls[0]
            self.assertEqual(call["url"], "https://example.test/v1/chat/completions")
            self.assertEqual(call["headers"]["Authorization"], "Bearer secret")
            self.assertEqual(call["json"]["model"], "vision-model")
            content = call["json"]["messages"][0]["content"]
            self.assertEqual(content[0]["text"], "caption it")
            self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_api_tagger_writes_nl_caption_with_fragment_edits(self):
        class StaticClient:
            def caption(self, image_path):
                return "a girl, lowres\nstanding"

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "a.png"
            self.make_image(image_path)

            result = service.run_api_tagger(
                str(root),
                client=StaticClient(),
                additional_tags="best quality",
                exclude_tags="lowres",
                on_conflict="copy",
            )

            self.assertEqual(result.processed, 1)
            self.assertEqual(
                image_path.with_suffix(".txt").read_text(encoding="utf-8"),
                "a girl, standing, best quality",
            )

    def test_caption_tagger_reuses_folder_writer_for_local_nl_models(self):
        class StaticCaptionClient:
            def caption(self, image_path):
                return "a small test image"

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "a.png"
            self.make_image(image_path)

            result = service.run_caption_tagger(
                str(root),
                client=StaticCaptionClient(),
                additional_tags="training caption",
                on_conflict="copy",
            )

            self.assertEqual(result.processed, 1)
            self.assertEqual(
                image_path.with_suffix(".txt").read_text(encoding="utf-8"),
                "a small test image, training caption",
            )

    def test_cli_exposes_local_api_and_caption_modes(self):
        parser = cli.build_parser()

        local_args = parser.parse_args(["local", "--path", "input"])
        api_args = parser.parse_args(["api", "--path", "input", "--model", "vision"])
        caption_args = parser.parse_args(["caption", "--path", "input"])

        self.assertEqual(local_args.command, "local")
        self.assertEqual(api_args.command, "api")
        self.assertEqual(caption_args.command, "caption")
        self.assertEqual(caption_args.model, service.DEFAULT_LOCAL_CAPTION_MODEL)

    def test_local_tagger_files_can_be_resolved_from_user_directory(self):
        old_value = os.environ.get("MIKAZUKI_TAGGER_DIR")
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                model_dir = root / "wd14-convnextv2-v2"
                model_dir.mkdir()
                (model_dir / "model.onnx").write_bytes(b"fake onnx")
                (model_dir / "selected_tags.csv").write_text("name\nfake_tag\n", encoding="utf-8")

                os.environ["MIKAZUKI_TAGGER_DIR"] = str(root)
                resolved = local_models.resolve_local_tagger_files(
                    "wd14-convnextv2-v2",
                    ["model.onnx", "selected_tags.csv"],
                )

                self.assertEqual(resolved, (model_dir / "model.onnx", model_dir / "selected_tags.csv"))
        finally:
            if old_value is None:
                os.environ.pop("MIKAZUKI_TAGGER_DIR", None)
            else:
                os.environ["MIKAZUKI_TAGGER_DIR"] = old_value

    def test_hf_download_config_uses_project_cache_and_optional_mirror(self):
        old_home = os.environ.get("HF_HOME")
        old_endpoint = os.environ.get("HF_ENDPOINT")
        try:
            os.environ.pop("HF_HOME", None)
            os.environ.pop("HF_ENDPOINT", None)

            hf_home = service.configure_hf_download(use_cn_mirror=True)

            self.assertEqual(hf_home, (service.REPO_ROOT / "huggingface").resolve())
            self.assertEqual(os.environ["HF_HOME"], str((service.REPO_ROOT / "huggingface").resolve()))
            self.assertEqual(os.environ["HF_ENDPOINT"], "https://hf-mirror.com")
        finally:
            if old_home is None:
                os.environ.pop("HF_HOME", None)
            else:
                os.environ["HF_HOME"] = old_home
            if old_endpoint is None:
                os.environ.pop("HF_ENDPOINT", None)
            else:
                os.environ["HF_ENDPOINT"] = old_endpoint

    def test_api_key_explicit_value_takes_precedence_over_environment(self):
        old_value = os.environ.get("TAGGER_TEST_KEY")
        os.environ["TAGGER_TEST_KEY"] = "from-env"
        try:
            self.assertEqual(resolve_api_key("explicit", "TAGGER_TEST_KEY"), "explicit")
            self.assertEqual(resolve_api_key(None, "TAGGER_TEST_KEY"), "from-env")
        finally:
            if old_value is None:
                os.environ.pop("TAGGER_TEST_KEY", None)
            else:
                os.environ["TAGGER_TEST_KEY"] = old_value


if __name__ == "__main__":
    unittest.main()
