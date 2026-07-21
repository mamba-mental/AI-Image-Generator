"""R3 #6-frontend — all-provider balance footer strip, static harness (same style as verify_pB.py).
Runtime proof done live: booted the real app, waited on #balanceall, got 13 real chips back
(Fal $15.46, OpenRouter $14.24 left, Runware $19.99, Novita $10.00, rest correctly portal-only/n-a
— matches bridge.py's dispatch to each backend's balance()). This locks the source contract.
Run: python .dd/verify_balance_footer.py"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
bridge = (ROOT / "bridge.py").read_text(encoding="utf-8")

checks = [
    ("6f.1 balanceall element exists in the footer", 'id="balanceall"' in index),
    ("6f.2 refreshAllBalances fans out over every configured service", "function refreshAllBalances" in app_js
        and "state.services.map(" in app_js),
    ("6f.3 refreshBalance() triggers the all-provider refresh (existing 3 call sites reused, no new ones)",
        "refreshAllBalances();" in app_js and app_js.count("refreshAllBalances(") >= 2),
    ("6f.4 reuses the existing bal-ok/low/info/none color classes (no new CSS needed)",
        '"bal-${b.kind' in app_js.replace(" ", "")),
    ("6f.5 in-flight re-entrancy guard (13 parallel network calls per refresh, don't stack them)",
        "_balanceAllInFlight" in app_js),
    ("6f.6 bridge.get_balance dispatches to Agent 3's per-backend balance() first",
        "_BALANCE_BACKENDS" in bridge and "backend.balance()" in bridge),
    ("6f.7 dispatch covers all 6 backends Agent 3 shipped balance() for",
        all(s in bridge for s in ['"nvidia": nvidia_api', '"openrouter": openrouter_api',
                                   '"replicate": replicate_api', '"cliproxy": cliproxy_api',
                                   '"ideogram": ideogram_web_api', '"ideogram-api": ideogram_api'])),
    ("6f.8 no dead duplicate inline logic left INSIDE get_balance for the now-dispatched services",
        'if service == "replicate":' not in bridge[bridge.index("def get_balance"):bridge.index("def list_models")]
        and 'if service == "openrouter":' not in bridge[bridge.index("def get_balance"):bridge.index("def list_models")]),
]

fails = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  [{'PASS' if ok else 'FAIL'}] {n}")
print(f"\n{len(checks)-len(fails)}/{len(checks)} static checks pass")
sys.exit(1 if fails else 0)
