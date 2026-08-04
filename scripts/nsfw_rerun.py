"""Versioned, date-stamped NSFW sweep re-run — the shared CORE all three triggers call
(the /nsfw-sweep command, the dashboard button, and a direct CLI).

Runs a Test 1 (fal-only, fine-art gallery) or Test 2 (multi-provider capability sweep) on a
NEW prompt WITHOUT clobbering the canonical datasets: every run gets a deterministic
`<YYYY-MM-DD>-<8-char prompt-sha>` tag, writes to tagged files/dirs, and appends a record to the
run manifest (dashboards/data/nsfw-runs.json) so the page's run-picker can offer every past run.

  # DRY-RUN is the DEFAULT — spends nothing, prints scope + $ estimate + would-write paths:
  python scripts/nsfw_rerun.py --prompt "<text>" --test 2
  python scripts/nsfw_rerun.py --prompt "<text>" --test 1 --dry-run

  # REAL run (SPENDS money) requires an explicit --go AND no --dry-run:
  python scripts/nsfw_rerun.py --prompt "<text>" --test 2 --go
  python scripts/nsfw_rerun.py --prompt "<text>" --test 1 --go --providers fal --limit 5

Safety: a real run fires ONLY on `--go` (and never when --dry-run is also passed). A bare call,
or any call with --dry-run, is always a cost-free preview. Test 2 full sweep ≈ $9-10; Test 1 ≈ <$1.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

REPO = Path(__file__).resolve().parent.parent          # the AI-Image-Generator repo root
COWORK = Path(r"C:/AI CoWork")
DASH = COWORK / "dashboards"
DATA = DASH / "data"
RUNS_MANIFEST = DATA / "nsfw-runs.json"

SWEEP = REPO / "scripts" / "nsfw_sweep.py"             # Test 2 capability sweep
GALLERY = REPO / "scripts" / "gen_verified_gallery.py"  # Test 1 fal gallery
CONSOLE = COWORK / "scripts" / "build_nsfw_console.py"  # capability -> console dataset

# Fallback estimate constants (mirror nsfw_sweep.py); the live import path uses the real values.
N_RENDERS = 3
EST_PRICE = 0.013          # ~$/gen incl. classifier (Test 2)
EST_PRICE_T1 = 0.012       # ~$/gen (Test 1, fal, 1 render/model)


def prompt_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_tag(text: str, given: str | None) -> str:
    if given and given.strip():
        return given.strip()
    return f"{time.strftime('%Y-%m-%d')}-{prompt_sha(text)[:8]}"


def _test2_scope(providers: list[str]) -> tuple[int, str]:
    """(#models a fresh-prompt Test-2 run would test, source-note). Live scope if importable,
    else a network-free estimate from the last capability file. Never spends."""
    try:
        sys.path.insert(0, str(REPO / "scripts"))
        import nsfw_sweep  # noqa: E402  (heavy import; may fail without app deps)
        scope, _skipped, _api = nsfw_sweep.build_scope(providers)
        return len(scope), "live scope"
    except Exception as e:  # noqa: BLE001 — degrade to the last capability count
        cap = REPO / "engine" / "nsfw_capability.json"
        try:
            n = len(json.loads(cap.read_text(encoding="utf-8")).get("models", {}))
            return n, f"estimate from last capability file ({type(e).__name__})"
        except Exception:  # noqa: BLE001
            return 0, f"scope unavailable ({type(e).__name__})"


def _test1_scope() -> tuple[int, str]:
    """(#fal-verified models a Test-1 gallery would render). Network-free — reads the capability."""
    cap = REPO / "engine" / "nsfw_capability.json"
    try:
        models = json.loads(cap.read_text(encoding="utf-8")).get("models", {})
        n = sum(1 for k, v in models.items()
                if v.get("grade") == "verified"
                and (v.get("provider") or (k.split(":", 1)[0] if ":" in k else "fal")) == "fal")
        return n, "fal-verified from capability"
    except Exception as e:  # noqa: BLE001
        return 0, f"scope unavailable ({type(e).__name__})"


def _would_write(test: int, tag: str) -> dict:
    if test == 2:
        return {
            "capability": str(REPO / "engine" / f"nsfw_capability_{tag}.json"),
            "console_dataset": str(DATA / f"nsfw-verified-{tag}.json"),
            "images": str(DASH / "assets" / "nsfw-verified" / tag) + "/",
            "run_manifest": str(RUNS_MANIFEST),
        }
    return {
        "console_dataset": str(DATA / f"nsfw-verified-test1-{tag}.json"),
        "images": str(DASH / "nsfw-img" / tag) + "/",
        "run_manifest": str(RUNS_MANIFEST),
    }


def dry_run(test: int, prompt: str, tag: str, providers: list[str], limit: int) -> int:
    if test == 2:
        n, src = _test2_scope(providers)
        gens = (min(n, limit) if limit else n) * N_RENDERS
        est = gens * EST_PRICE
        scope_line = (f"{min(n, limit) if limit else n} models × {N_RENDERS} renders "
                      f"≈ {gens} gens  ({src})")
    else:
        n, src = _test2_scope(providers)   # Test 1 now = full multi-provider sweep (editorial prompt)
        cnt = min(n, limit) if limit else n
        gens = cnt * N_RENDERS
        est = gens * EST_PRICE
        scope_line = f"{cnt} models × {N_RENDERS} renders ≈ {gens} gens  ({src})"

    print("── NSFW versioned re-run · DRY-RUN (no gens, spends nothing) ──")
    print(f"test        : {test}  ({'multi-provider capability sweep' if test == 2 else 'fal fine-art gallery'})")
    print(f"prompt      : {prompt[:120]}{'…' if len(prompt) > 120 else ''}")
    print(f"prompt sha  : {prompt_sha(prompt)[:16]}")
    print(f"tag         : {tag}")
    if test in (1, 2):
        print(f"providers   : {','.join(providers)}")
    if limit:
        print(f"limit       : {limit}")
    print(f"scope       : {scope_line}")
    print(f"SPEND EST   : ≈ ${est:.2f}")
    print("would write :")
    for k, v in _would_write(test, tag).items():
        print(f"   {k:16s} {v}")
    print("\n--dry-run: nothing generated. Add --go (without --dry-run) to SPEND.")
    return 0


def _run(cmd: list[str], cwd: Path) -> None:
    print("+ " + " ".join(str(c) for c in cmd), flush=True)
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    subprocess.run([str(c) for c in cmd], cwd=str(cwd), check=True,
                   stderr=subprocess.STDOUT, env=env)


def _append_manifest(record: dict) -> None:
    RUNS_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    runs = []
    if RUNS_MANIFEST.exists():
        try:
            runs = json.loads(RUNS_MANIFEST.read_text(encoding="utf-8"))
            if not isinstance(runs, list):
                runs = []
        except Exception:  # noqa: BLE001
            runs = []
    # de-dup on (test, tag): a re-run of the same prompt on the same day replaces its record
    runs = [r for r in runs if not (r.get("test") == record["test"] and r.get("tag") == record["tag"])]
    runs.insert(0, record)                              # newest first
    RUNS_MANIFEST.write_text(json.dumps(runs, indent=1), encoding="utf-8")
    print(f"manifest    : {RUNS_MANIFEST}  ({len(runs)} runs)")


def real_run(test: int, prompt: str, tag: str, providers: list[str], limit: int) -> int:
    py = sys.executable
    date = time.strftime("%Y-%m-%d")
    if test == 2:
        cap_out = REPO / "engine" / f"nsfw_capability_{tag}.json"
        sweep = [py, SWEEP, "--recheck", "--prompt", prompt,
                 "--out", cap_out, "--providers", ",".join(providers)]
        if limit:
            sweep += ["--limit", str(limit)]
        _run(sweep, REPO)
        _run([py, CONSOLE, "--capability", cap_out, "--tag", tag], COWORK)
        data_rel = f"data/nsfw-verified-{tag}.json"
        image_dir = f"assets/nsfw-verified/{tag}/"
        built = DATA / f"nsfw-verified-{tag}.json"
    else:  # Test 1 — full multi-provider sweep on the editorial prompt (all models), keep every image
        cap_out = REPO / "engine" / f"nsfw_capability_test1_{tag}.json"
        sweep = [py, SWEEP, "--recheck", "--prompt", prompt, "--out", cap_out,
                 "--providers", ",".join(providers)]
        if limit:
            sweep += ["--limit", str(limit)]
        _run(sweep, REPO)
        _run([py, CONSOLE, "--capability", cap_out, "--tag", tag, "--test1",
              "--prompt-text", prompt], COWORK)
        data_rel = f"data/nsfw-verified-test1-{tag}.json"
        image_dir = f"assets/nsfw-verified/{tag}/"
        built = DATA / f"nsfw-verified-test1-{tag}.json"

    verified_count = tested_total = None
    try:
        d = json.loads(built.read_text(encoding="utf-8"))
        verified_count = d.get("verified_count")
        tested_total = d.get("tested_total")
    except Exception:  # noqa: BLE001
        pass

    _append_manifest({
        "test": test, "tag": tag, "prompt": prompt, "prompt_sha": prompt_sha(prompt),
        "date": date, "verified_count": verified_count, "tested_total": tested_total,
        "data_path": data_rel, "image_dir": image_dir,
    })
    print(f"\nDONE · test {test} · tag {tag} · dataset {built.name} "
          f"(verified {verified_count}/{tested_total})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Versioned, date-stamped NSFW sweep re-run (dry-run by default).")
    ap.add_argument("--prompt", required=True, help="the new prompt to sweep on")
    ap.add_argument("--test", type=int, choices=(1, 2), required=True,
                    help="1 = fal fine-art gallery (~<$1); 2 = multi-provider capability sweep (~$9-10)")
    ap.add_argument("--tag", default=None, help="override the auto <date>-<sha8> version tag")
    ap.add_argument("--providers", default="fal,together,agnes,novita,runware",
                    help="Test-2 provider scope (Test 1 is always fal-only)")
    ap.add_argument("--limit", type=int, default=0, help="cap models tested (smoke); 0 = all")
    ap.add_argument("--dry-run", action="store_true", help="force a cost-free preview (default when no --go)")
    ap.add_argument("--go", action="store_true", help="actually SPEND and perform the real sweep")
    args = ap.parse_args()

    prompt = args.prompt.strip()
    if not prompt:
        print("error: --prompt is empty", file=sys.stderr)
        return 2
    tag = make_tag(prompt, args.tag)
    providers = [p.strip() for p in args.providers.split(",") if p.strip()]

    is_real = args.go and not args.dry_run            # safety: --go alone; --dry-run always wins
    if not is_real:
        return dry_run(args.test, prompt, tag, providers, args.limit)
    return real_run(args.test, prompt, tag, providers, args.limit)


if __name__ == "__main__":
    sys.exit(main())
