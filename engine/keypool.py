"""Per-provider API-key pool with round-robin failover (#13).

Keys are sourced ONLY from env/config — never hardcoded. A pool is built from, in order:
  1. the config field (a single string or a list),
  2. the primary env var (e.g. NVIDIA_API_KEY),
  3. a comma-separated pool env var (<ENV>S or <ENV>_POOL),
  4. numbered env vars <ENV>_2 .. <ENV>_9.
On a rate-limit/auth failure the job rotates to the next key and retries (see jobs._run).
The active key is mirrored into os.environ[<ENV>] so the existing backends pick it up unchanged.
"""
import os
import threading

_LOCK = threading.Lock()
_POOLS = {}   # service -> {"keys": [...], "env": ENV_NAME, "idx": 0}


def build(service: str, env_name: str, config_val="") -> int:
    keys = []
    if isinstance(config_val, list):
        keys += [k for k in config_val if k]
    elif config_val:
        keys.append(config_val)
    if os.environ.get(env_name):
        keys.append(os.environ[env_name])
    for extra in (env_name + "S", env_name + "_POOL"):
        if os.environ.get(extra):
            keys += [k.strip() for k in os.environ[extra].split(",") if k.strip()]
    for i in range(2, 10):
        v = os.environ.get(f"{env_name}_{i}")
        if v:
            keys.append(v)
    seen = set()
    keys = [k for k in keys if not (k in seen or seen.add(k))]  # dedupe, keep order
    with _LOCK:
        _POOLS[service] = {"keys": keys, "env": env_name, "idx": 0}
        if keys:
            os.environ[env_name] = keys[0]
    return len(keys)


def size(service: str) -> int:
    with _LOCK:
        return len(_POOLS.get(service, {}).get("keys", []))


def current(service: str) -> str:
    with _LOCK:
        p = _POOLS.get(service)
        return p["keys"][p["idx"]] if p and p["keys"] else ""


def index(service: str) -> int:
    with _LOCK:
        return _POOLS.get(service, {}).get("idx", 0)


def rotate(service: str) -> bool:
    """Advance to the next key and mirror it into the env. False if <2 keys."""
    with _LOCK:
        p = _POOLS.get(service)
        if not p or len(p["keys"]) < 2:
            return False
        p["idx"] = (p["idx"] + 1) % len(p["keys"])
        os.environ[p["env"]] = p["keys"][p["idx"]]
        return True
