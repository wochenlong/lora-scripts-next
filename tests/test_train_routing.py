import ast
import unittest
from pathlib import Path


def load_trainer_mapping() -> dict[str, str]:
    source = Path("mikazuki/app/api.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "trainer_mapping":
                    return ast.literal_eval(node.value)
    raise AssertionError("trainer_mapping not found in mikazuki/app/api.py")


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
        self.assertEqual(mapping["sdxl-lora"], "./scripts/stable/sdxl_train_network.py")


if __name__ == "__main__":
    unittest.main()
