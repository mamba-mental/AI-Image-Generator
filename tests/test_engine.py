"""Engine unit tests: key resolution order + output-path/save behavior. No network."""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import config as engine_config
from engine.save import make_output_paths, persist_results


class TestKeyResolution(unittest.TestCase):

    def test_config_wins_over_env(self):
        os.environ["REPLICATE_API_TOKEN"] = "env-value"
        got = engine_config._resolve_one({"replicate_api_key": "config-value"},
                                         "replicate_api_key", "REPLICATE_API_TOKEN")
        self.assertEqual(got, "config-value")

    def test_placeholder_falls_back_to_env(self):
        os.environ["REPLICATE_API_TOKEN"] = "env-value"
        got = engine_config._resolve_one({"replicate_api_key": "YOUR_REPLICATE_API_TOKEN_HERE"},
                                         "replicate_api_key", "REPLICATE_API_TOKEN")
        self.assertEqual(got, "env-value")

    def test_empty_config_falls_back_to_env(self):
        os.environ["GEMINI_API_KEY"] = "env-gem"
        got = engine_config._resolve_one({}, "gemini_api_key", "GEMINI_API_KEY")
        self.assertEqual(got, "env-gem")


class TestSave(unittest.TestCase):

    def test_output_paths_batch_naming(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            paths = make_output_paths(td, 3)
            self.assertEqual(len(paths), 3)
            self.assertTrue(paths[0].endswith("_1.png"))
            self.assertTrue(all(p.startswith(td) for p in paths))

    def test_error_strings_collected_not_saved(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            saved, errors = persist_results(["HF Error: boom"], make_output_paths(td, 1))
            self.assertEqual(saved, [])
            self.assertEqual(len(errors), 1)

    def test_pil_image_saved(self):
        import tempfile
        from PIL import Image
        with tempfile.TemporaryDirectory() as td:
            img = Image.new("RGB", (4, 4), "black")
            saved, errors = persist_results([img], make_output_paths(td, 1))
            self.assertEqual(len(saved), 1)
            self.assertTrue(os.path.exists(saved[0]))
            self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
