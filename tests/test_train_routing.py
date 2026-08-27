import ast
import unittest
from pathlib import Path


def load_trainer_mapping() -> dict[str, str]:
    source = Path("mikazuki/engines/kohya/run.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "TRAINER_MAPPING":
                    return ast.literal_eval(node.value)
    raise AssertionError("TRAINER_MAPPING not found in mikazuki/engines/kohya/run.py")


class TrainRoutingTests(unittest.TestCase):
    def test_anima_train_type_routes_to_stable_wrapper(self):
        mapping = load_trainer_mapping()

        self.assertEqual(mapping["anima-lora"], "./scripts/dev/anima_train_network.py")

    def test_legacy_sd3_train_type_routes_to_anima_wrapper(self):
        mapping = load_trainer_mapping()

        self.assertEqual(mapping["sd3-lora"], "./scripts/dev/anima_train_network.py")

    def test_anima_finetune_routes_to_full_train_wrapper(self):
        mapping = load_trainer_mapping()

        self.assertEqual(mapping["anima-finetune"], "./scripts/dev/anima_train.py")

    def test_standard_training_routes_are_unchanged(self):
        mapping = load_trainer_mapping()

        self.assertEqual(mapping["sd-lora"], "./scripts/stable/train_network.py")
        self.assertEqual(mapping["sdxl-lora"], "./vendor/sd-scripts/sdxl_train_network.py")


if __name__ == "__main__":
    unittest.main()
