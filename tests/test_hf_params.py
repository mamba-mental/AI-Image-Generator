"""Migrated from test_app.py — targets engine.backends.hf_api.configure_hf_api_params.

The old test's expectations were stale against the evolved implementation (asserted
':1.4' emphasis where the code writes ':1.8', expected 'nsfw' inside a base string that
never contained it). These assertions match the real, ported behavior.
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.backends.hf_api import configure_hf_api_params


class TestConfigureHfApiParams(unittest.TestCase):

    def test_base_negative_added_when_absent(self):
        params = configure_hf_api_params({"prompt": "test prompt"})
        self.assertIn("negative_prompt", params)
        for term in ("watermark", "censored", "safety checker"):
            self.assertIn(term, params["negative_prompt"])

    def test_safety_keywords_appended_to_prompt(self):
        params = configure_hf_api_params({"prompt": "test prompt"})
        self.assertIn("(perfectly acceptable content:1.8)", params["prompt"])

    def test_safety_keywords_not_duplicated(self):
        once = configure_hf_api_params({"prompt": "test prompt"})
        twice = configure_hf_api_params(once.copy())
        self.assertEqual(twice["prompt"].count("(perfectly acceptable content"), 1)

    def test_user_negative_preserved_in_merge(self):
        params = configure_hf_api_params({"prompt": "p", "negative_prompt": "user negative"})
        self.assertIn("user negative", params["negative_prompt"])
        self.assertIn("watermark", params["negative_prompt"])

    def test_env_flag_set(self):
        configure_hf_api_params({"prompt": "p"})
        self.assertEqual(os.environ.get("HF_DISABLE_SAFETY"), "true")


if __name__ == "__main__":
    unittest.main()
