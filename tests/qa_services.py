"""Service smoke — call each backend's generate() with what the UI actually sends,
classify OK / EXTERNAL (billing/quota/cold-start, not a code bug) / CODEBUG."""
import sys, re, time
sys.path.insert(0, ".")
from engine.backends import BACKENDS

# (service, model, params-as-the-UI-sends) — cheap models only
CASES = [
    ("fal",         "fal-ai/flux/schnell",              {"prompt": "a red leaf on white", "num_images": 1}),
    ("fal",         "fal-ai/elevenlabs/tts/turbo-v2.5", {"prompt": "hello world, this is a test"}),  # tts wants 'text' not 'prompt'?
    ("openai",      "gpt-image-2",                       {"prompt": "a red leaf on white"}),
    ("gemini",      "gemini-2.5-flash-image",            {"prompt": "a red leaf on white"}),
    ("huggingface", "black-forest-labs/FLUX.1-schnell",  {"prompt": "a red leaf on white"}),
    ("replicate",   "black-forest-labs/flux-schnell",    {"prompt": "a red leaf on white"}),
    ("nvidia",      "black-forest-labs/flux.1-dev",      {"prompt": "a red leaf on white"}),
]
EXTERNAL = re.compile(r"402|500|internal server|502|503|billing|quota|429|too many|rate.?limit|cold.?start|timeout|insufficient|payment|credit", re.I)

def classify(res):
    if not res:
        return "CODEBUG", "empty result list"
    first = res[0]
    if isinstance(first, str) and ("Error" in first or "error" in first):
        return ("EXTERNAL" if EXTERNAL.search(first) else "CODEBUG"), first[:180]
    # a real output: URL string, PIL image, or bytes tuple
    kind = type(first).__name__
    val = first[:80] if isinstance(first, str) else kind
    return "OK", val

for svc, model, params in CASES:
    t = time.time()
    try:
        res = BACKENDS[svc](model, params, progress=lambda m: None)
        status, detail = classify(res)
    except Exception as e:
        status, detail = "CODEBUG", f"{type(e).__name__}: {e}"[:180]
    print(f"{svc:12} {model:34} {time.time()-t:5.0f}s  {status:9} {detail}")
