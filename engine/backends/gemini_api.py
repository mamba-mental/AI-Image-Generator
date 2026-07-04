"""Gemini backend — port of app.py _call_gemini_api (:2046). Raw urllib kept (no SDK dep).

Returns a list of PIL Images / "Gemini Error: ..." strings (one per requested output).
"""
import base64
import io
import json
import os
import ssl
import traceback
import urllib.error
import urllib.request

from PIL import Image


def _call_once(model_id: str, params: dict):
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if not gemini_key:
        return "Gemini Error: API Key not configured. Set GEMINI_API_KEY in .env or configure via UI."

    prompt_text = params.get("prompt", "")
    if not prompt_text:
        return "Gemini Error: No prompt provided."

    full_prompt = f"Generate an image: {prompt_text}"
    width, height = params.get("width", 1024), params.get("height", 1024)
    if width and height and width != height:
        orientation = "Landscape" if width > height else "Portrait"
        full_prompt += f". {orientation} aspect ratio approximately {width}:{height}."

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={gemini_key}"
    request_body = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    req = urllib.request.Request(url, data=json.dumps(request_body).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")

    try:
        resp = urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=120)
        data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        if e.code == 429:
            return ("Gemini Error: Rate limit exceeded (429). Try a different API key or wait "
                    f"for quota reset at midnight Pacific. {error_body[:200]}")
        if e.code == 400:
            return f"Gemini Error: Bad request (400). {error_body[:300]}"
        return f"Gemini Error: HTTP {e.code} - {error_body[:300]}"
    except urllib.error.URLError as e:
        return f"Gemini Error: Connection failed - {e}"
    except json.JSONDecodeError as e:
        return f"Gemini Error: Failed to parse API response - {e}"

    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            if "inlineData" in part:
                img_bytes = base64.b64decode(part["inlineData"]["data"])
                return Image.open(io.BytesIO(img_bytes))

    text_parts = [part["text"]
                  for candidate in data.get("candidates", [])
                  for part in candidate.get("content", {}).get("parts", [])
                  if "text" in part]
    if text_parts:
        return f"Gemini Error: Model returned text instead of image - {' '.join(text_parts)[:300]}"
    return "Gemini Error: No image data in response."


def generate(model_id: str, params: dict, progress=None, cancel_event=None) -> list:
    model_id = model_id or params.get("model_id", "gemini-2.5-flash-image")
    num_outputs = params.get("num_outputs", 1)
    results = []
    for i in range(num_outputs):
        if cancel_event is not None and cancel_event.is_set():
            results.append("Gemini Error: Cancelled.")
            break
        if progress:
            progress(f"Generating image {i + 1}/{num_outputs} (Gemini)...")
        try:
            results.append(_call_once(model_id, params))
        except Exception as e:
            traceback.print_exc()
            results.append(f"Gemini Error: {e}")
    return results
