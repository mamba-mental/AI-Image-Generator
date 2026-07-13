"""Provider adapter interface. One small contract every backend implements."""
import os


class Provider:
    name = ""       # short id, e.g. "fal"
    label = ""      # display, e.g. "fal.ai"
    key_env = ""    # env var that must be set for this provider to be usable

    def ready(self) -> bool:
        return bool(os.environ.get(self.key_env)) if self.key_env else True

    def list_models(self, kind=None) -> list:
        """Return [{id, label, kind}] where kind in ('image','video'). kind filters."""
        raise NotImplementedError

    def form_spec(self, model_id) -> list:
        """Return a FormSpec (schema.py shape) for this model's parameters."""
        raise NotImplementedError

    def submit(self, model_id, params: dict) -> dict:
        """Run a generation. Return {'files': [paths]} or {'error': str}."""
        raise NotImplementedError
