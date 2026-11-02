"""E2E (Edge): import 100 FICTITIOUS products -> classify -> review -> photo pendencies; sidebar fit at 1366x768.
Usage: .venv/Scripts/python apps/web/e2e/catalog_flow.py <out_dir> <base_url>
"""
import pathlib
import sys
import tempfile
import uuid

from playwright.sync_api import expect, sync_playwright

OUT, BASE = pathlib.Path(sys.argv[1]), sys.argv[2]
OUT.mkdir(parents=True, exist_ok=True)
EMAIL = f"catalogo-{uuid.uuid4().hex[:6]}@example.com"
expect.set_options(timeout=60_000)
KINDS = [("Pastilha de freio dianteira", "Freios"), ("Filtro de óleo", "Motor"), ("Carrinho de controle remoto", "Brinquedos"),
         ("Camiseta manga curta", "Moda"), ("Vaso decorativo", "Casa"), ("Produto genérico", "")]


def gtin13(n: int) -> str:
    body = f"0{789000000000 + n:012d}"[-12:]
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(body))
    return body + str((10 - total % 10) % 10)


rows = ["Código interno;Descrição curta;EAN;Marca;Preço;Saldo"]
for i in range(100):
    name, _ = KINDS[i % len(KINDS)]
    rows.append(f"0{i:04d};{name} {i};{gtin13(i)};{'Marca Demo' if i % 3 else ''};{19 + i % 40},90;{i % 9}")
csv_path = pathlib.Path(tempfile.mkdtemp()) / "base-ficticia-100.csv"
csv_path.write_text("\n".join(rows), encoding="utf-8")
errors = []

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_context(viewport={"width": 1440, "height": 900}, locale="pt-BR").new_page()
    page.set_default_timeout(120_000)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE + "/cadastro/")
    page.get_by_label("Seu nome").fill("Operador Catálogo")
    page.get_by_label("Empresa").fill("Catálogo Demo")
    page.get_by_label("E-mail").fill(EMAIL)
    page.get_by_label("Senha").fill("senha-forte-123")
    page.get_by_role("button", name="Criar conta").click()
    page.wait_for_url("**/painel/")

    page.goto(BASE + "/catalogo/")
    page.get_by_role("link", name="Importar produtos").click()
    page.wait_for_url("**/importacoes/")
    with page.expect_file_chooser() as fc:
        page.get_by_role("button", name="Escolher arquivo").click()
    fc.value.set_files(str(csv_path))
    expect(page.get_by_label("Campo para EAN")).to_have_value("gtin")
    expect(page.get_by_label("Campo para Código interno")).to_have_value("sku")
    expect(page.get_by_label("Campo para Saldo")).to_have_value("stock")
    shot = lambda n: page.screenshot(path=str(OUT / f"{n}.png"), full_page=True)  # noqa: E731
    shot("50-import-mapping")
    page.get_by_role("button", name="3. Simular importação").click()
    expect(page.get_by_text("nada foi gravado ainda")).to_be_visible()
    page.get_by_role("button", name="Confirmar e importar 100 item(ns)").click()
    expect(page.get_by_text("Concluído: 100 criado(s)", exact=False)).to_be_visible()
    shot("51-import-done")

    page.goto(BASE + "/catalogo/")
    page.get_by_placeholder("Buscar por nome").fill("00007")
    expect(page.get_by_role("cell", name="00007", exact=True)).to_be_visible()  # leading zeros kept

    page.goto(BASE + "/categorias/")
    page.get_by_role("button", name="Criar árvore de exemplo").click()
    expect(page.get_by_text("categorias de exemplo criadas", exact=False)).to_be_visible()
    page.get_by_role("button", name="Classificar produtos").click()
    expect(page.get_by_text("Classificação:", exact=False)).to_be_visible()
    summary = page.get_by_text("Classificação:", exact=False).inner_text()
    shot("52-classification")
    page.get_by_label("Visão").select_option("review")
    first_box = page.get_by_role("checkbox").first
    first_box.check()
    page.get_by_role("button", name="Aceitar sugestões").click()
    expect(page.get_by_text("sugestão(ões) aceita(s)", exact=False)).to_be_visible()

    page.goto(BASE + "/fotos/")
    expect(page.get_by_text("sem imagem aprovada").first).to_be_visible()

    sizes = {}
    for channel in ("msedge", "chrome"):
        b2 = p.chromium.launch(channel=channel, headless=True)
        ctx2 = b2.new_context(viewport={"width": 1366, "height": 768}, storage_state=page.context.storage_state())
        pg = ctx2.new_page()
        pg.set_default_timeout(120_000)
        pg.goto(BASE + "/painel/")
        pg.wait_for_timeout(1500)
        sizes[channel] = pg.evaluate("""() => { const a = document.querySelector('aside nav').parentElement;
            return {scrolls: a.scrollHeight > a.clientHeight}; }""")
        pg.screenshot(path=str(OUT / f"53-sidebar-{channel}.png"))
        b2.close()
    browser.close()

print("classification:", summary)
print("sidebar scroll at 1366x768:", sizes)
print("page errors:", errors)
print("CATALOG E2E OK")
