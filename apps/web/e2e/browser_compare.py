"""Edge vs Chrome: same screens, same sizes; collects layout metrics (fonts, scrollbar, widths, overflow) and
screenshots. Uses the demo account of the local dev database (fictitious data).
Usage: .venv/Scripts/python apps/web/e2e/browser_compare.py <out_dir> [base_url]
"""
import json
import pathlib
import sys

from playwright.sync_api import sync_playwright

OUT = pathlib.Path(sys.argv[1])
BASE = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:3000"
OUT.mkdir(parents=True, exist_ok=True)
SIZES = [(1366, 768), (1440, 900), (1920, 1080)]
PAGES = ["/painel/", "/catalogo/", "/templates/", "/assistente/"]
METRICS = """() => {
  const r = (el) => el ? Math.round(el.getBoundingClientRect().width) : null;
  const body = getComputedStyle(document.body);
  const ctx = document.createElement('canvas').getContext('2d');
  ctx.font = `500 14px ${body.fontFamily}`;
  return {
    dpr: devicePixelRatio, scrollbar: innerWidth - document.documentElement.clientWidth,
    overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    fontFamily: body.fontFamily.split(',')[0], fontSize: body.fontSize,
    fontsLoaded: [...document.fonts].filter(f => f.status === 'loaded').map(f => f.family + ' ' + f.weight),
    textWidth: Math.round(ctx.measureText('Catálogo mestre da organização 1234567890').width * 10) / 10,
    sidebar: r(document.querySelector('aside')), main: r(document.querySelector('main')),
    h1: document.querySelector('h1') ? Math.round(document.querySelector('h1').getBoundingClientRect().height) : null,
    colorScheme: getComputedStyle(document.documentElement).colorScheme,
    scrollbarColor: getComputedStyle(document.documentElement).scrollbarColor,
  };
}"""

results = {}
with sync_playwright() as p:
    for channel in ("msedge", "chrome"):
        browser = p.chromium.launch(channel=channel, headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="pt-BR")
        page = ctx.new_page()
        page.set_default_timeout(120_000)
        page.goto(BASE + "/entrar/")
        page.get_by_label("E-mail").fill("demo@example.com")
        page.get_by_label("Senha").fill("demo-mla-2026")
        page.get_by_role("button", name="Entrar").click()
        page.wait_for_url("**/painel/")
        results[channel] = {"version": browser.version}
        for w, h in SIZES:
            page.set_viewport_size({"width": w, "height": h})
            for path in PAGES:
                page.goto(BASE + path)
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(400)
                key = f"{w}x{h} {path}"
                results[channel][key] = page.evaluate(METRICS)
                page.screenshot(path=str(OUT / f"{channel}-{w}x{h}-{path.strip('/') or 'home'}.png"))
        browser.close()

(OUT / "metrics.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
edge, chrome = results["msedge"], results["chrome"]
print("versions:", edge["version"], "|", chrome["version"])
for key in edge:
    if key == "version":
        continue
    diff = {k: (edge[key][k], chrome[key][k]) for k in edge[key] if edge[key][k] != chrome[key][k]}
    print(key, "DIFF:" if diff else "same", diff if diff else "")
