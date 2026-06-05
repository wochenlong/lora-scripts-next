import unittest
from pathlib import Path


class TrainSubmitLoadingStaticTests(unittest.TestCase):
    def test_standard_train_button_shows_immediate_submit_feedback(self):
        layout = Path("frontend/dist/assets/layout.96d49288.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("submitLoading=ref(!1)", layout)
        self.assertIn("setSubmitButtonLoading=", layout)
        self.assertIn("trainSubmitButton", layout)
        self.assertIn("if(submitLoading.value)return", layout)
        self.assertIn("submitLoading.value=!0", layout)
        self.assertIn("setSubmitButtonLoading(!0)", layout)
        self.assertIn("正在提交训练任务...", layout)
        self.assertIn("setSubmitButtonLoading(!1)", layout)
        self.assertIn('try{const _=parseParams(n.value(a.value),t);', layout)
        self.assertIn("finally{submitLoading.value=!1", layout)
        self.assertIn("loading:submitLoading.value", layout)
        self.assertIn("disabled:submitLoading.value", layout)


if __name__ == "__main__":
    unittest.main()
