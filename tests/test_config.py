import importlib
import os
import sys
import types
import unittest
from unittest.mock import patch


def load_config(env):
    dotenv = types.SimpleNamespace(load_dotenv=lambda: None)
    sys.modules.pop("modules.config", None)
    with patch.dict(os.environ, env, clear=True), patch.dict(sys.modules, {"dotenv": dotenv}):
        return importlib.import_module("modules.config")


class ConfigValidationTests(unittest.TestCase):
    def base_env(self):
        return {
            "API_ID": "123",
            "API_HASH": "hash",
            "TARGET_CHAT_ID": "-100123",
            "DEFAULT_API_KEY": "key",
        }

    def test_valid_required_config_loads(self):
        cfg = load_config(self.base_env())

        self.assertEqual(cfg.API_ID, 123)
        self.assertEqual(cfg.TARGET_CHAT_ID, -100123)
        self.assertEqual(cfg.USER_API_KEYS, {})

    def test_missing_required_config_exits(self):
        env = self.base_env()
        del env["API_HASH"]

        with self.assertRaisesRegex(SystemExit, "API_HASH"):
            load_config(env)

    def test_invalid_integer_config_exits(self):
        env = self.base_env()
        env["API_ID"] = "abc"

        with self.assertRaisesRegex(SystemExit, "API_ID"):
            load_config(env)

    def test_invalid_user_keys_json_exits(self):
        env = self.base_env()
        env["USER_API_KEYS_JSON"] = "{bad"

        with self.assertRaisesRegex(SystemExit, "USER_API_KEYS_JSON"):
            load_config(env)

    def test_user_keys_must_be_object(self):
        env = self.base_env()
        env["USER_API_KEYS_JSON"] = "[]"

        with self.assertRaisesRegex(SystemExit, "JSON object"):
            load_config(env)


if __name__ == "__main__":
    unittest.main()
