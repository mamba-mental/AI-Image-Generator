# *DD Contract: P1 — img2img blank tile (#4) + model-id 404s (#8)

Build type: bugfix · methods: atdd (regression gate) · edd (failing case = example) · tdd
Harness: `.dd/verify_p1_bugfix.py` (binary), + one LIVE kontext gen for #4.

## Acceptance
- AC-1 (#4): save._pick_ext(url, ct, dest) derives the extension from the URL path first, content-type
  fallback. url ".../x.jpg" + ct "application/octet-stream" -> ".jpg" (NOT ".bin"). url ".../v.mp4" -> ".mp4".
  url with no ext + ct "image/png" -> ".png". A real .glb url still -> ".glb". [RED]
- AC-2 (#4 live): one real fal-ai/flux-pro/kontext img2img gen saves a file with an image extension
  (.jpg/.png/.webp), NOT .bin. [RED, --live]
- AC-3 (#8 purge): the 8 dead ids appear 0 times in config.json AND config.default.json recent_models_*. [RED]
- AC-4 (#8 guard): bridge._normalize_model_id normalizes malformed ids — ("huggingface","huggingface.co/x/y")
  ->"x/y"; ("replicate","https://huggingface.co/a/b")->"a/b"; ("fal","fal-ai/flux/dev")->unchanged; empty->"". [RED]
- AC-5: `python main.py --smoke` exits 0. [RED]

## The 8 dead ids (from live audit)
openai: dall-e-3 · nvidia: stabilityai/stable-diffusion-3.5-large ·
replicate: huggingface.co/CultriX/flux-nsfw-highress, huggingface.co/lustlyai/Flux_Lustly.ai_Uncensored_nsfw_v1 ·
hf: black-forest-labs/flux-1.1-pro-ultra, huggingface.co/black-forest-labs/FLUX.1-dev,
    https://huggingface.co/CultriX/flux-nsfw-highress, huggingface.co/CultriX/flux-nsfw-highress

## Non-goals
- Auditing the ~149 non-image fal catalog models. Re-granting OpenAI dall-e access (removed per PRIME).

Status: CONTRACT SET (harness RED)
