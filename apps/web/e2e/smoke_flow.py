"""E2E smoke of MLA Web through Edge: register, dashboard, create/edit product, members, history, logout/login, phone.

Needs a running API that serves the static build (MLA_WEB_DIST_DIR=apps/web/out) and Playwright with Edge
(the desktop venv has both):  .venv/Scripts/python apps/web/e2e/smoke_flow.py <screenshot_dir> [base_url]
Uses a throwaway account per run; point it only at a development database.
"""
import os, sys, pathlib, uuid
from playwright.sync_api import sync_playwright, expect

BASE = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("MLA_E2E_BASE", "http://127.0.0.1:8000")
EMAIL = f"kelvin-{uuid.uuid4().hex[:6]}@example.com"
out = pathlib.Path(sys.argv[1]); out.mkdir(exist_ok=True)
console_errors = []

def shot(page, name):
    page.screenshot(path=str(out / f"{name}.png"), full_page=True)

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, locale="pt-BR")
    page = ctx.new_page()
    page.on("console", lambda m: m.type == "error" and console_errors.append(m.text))

    page.goto(BASE + "/")
    page.wait_for_url("**/entrar/**")
    shot(page, "01-login")
    page.get_by_role("link", name="Criar conta").click()
    page.get_by_label("Seu nome").fill("Kelvin Teste")
    page.get_by_label("Empresa").fill("Auto Peças Demo")
    page.get_by_label("E-mail").fill(EMAIL)
    page.get_by_label("Senha").fill("senha-forte-123")
    page.get_by_role("button", name="Criar conta").click()
    page.wait_for_url("**/painel/")
    expect(page.get_by_text("Seu catálogo está vazio")).to_be_visible()
    shot(page, "02-dashboard-empty")

    page.get_by_role("link", name="Produtos", exact=True).click()
    page.wait_for_url("**/catalogo/")
    for sku, name, brand, gtin, price in [("FO-100", "Filtro de óleo Tecfil PSL55", "Tecfil", "7891234567895", "25,90"),
                                          ("VL-200", "Vela de ignição NGK BKR6E", "NGK", "", "18,50"),
                                          ("PA-300", "Pastilha de freio dianteira", "", "7891234567890", "")]:
        page.get_by_role("button", name="Novo produto").click()
        dlg = page.get_by_role("dialog")
        dlg.get_by_label("SKU").fill(sku)
        dlg.get_by_label("Nome").fill(name)
        dlg.get_by_label("Marca").fill(brand)
        dlg.get_by_label("GTIN / EAN").fill(gtin)
        dlg.get_by_label("Preço de venda (R$)").fill(price)
        dlg.get_by_role("button", name="Salvar produto").click()
        expect(page.get_by_role("dialog")).to_have_count(0)
        expect(page.get_by_role("link", name=name)).to_be_visible()
    # Client-side validation: SKU with spaces is refused before reaching the API.
    page.get_by_role("button", name="Novo produto").click()
    dlg = page.get_by_role("dialog")
    dlg.get_by_label("SKU").fill("COM ESPACO")
    dlg.get_by_label("Nome").fill("x")
    dlg.get_by_role("button", name="Salvar produto").click()
    expect(dlg.get_by_text("O SKU não pode conter espaços.")).to_be_visible()
    shot(page, "03-create-validation")
    page.keyboard.press("Escape")
    # Duplicate SKU: server error surfaced in the form.
    page.get_by_role("button", name="Novo produto").click()
    dlg = page.get_by_role("dialog")
    dlg.get_by_label("SKU").fill("FO-100"); dlg.get_by_label("Nome").fill("dup")
    dlg.get_by_role("button", name="Salvar produto").click()
    expect(dlg.get_by_text("Já existe um produto com o SKU FO-100.")).to_be_visible()
    page.keyboard.press("Escape")
    shot(page, "04-catalog")

    page.get_by_placeholder("Buscar por nome").fill("ngk")
    expect(page.get_by_role("link", name="Vela de ignição NGK BKR6E")).to_be_visible()
    expect(page.get_by_role("link", name="Filtro de óleo Tecfil PSL55")).to_have_count(0)
    page.get_by_placeholder("Buscar por nome").fill("")

    page.get_by_role("link", name="Pastilha de freio dianteira").click()
    page.wait_for_url("**/catalogo/produto/**")
    expect(page.get_by_text("Preço de venda não informado.")).to_be_visible()
    page.get_by_label("Preço de venda (R$)").fill("89,90")
    page.get_by_label("Marca").fill("Cobreq")
    page.get_by_role("button", name="Salvar alterações").click()
    expect(page.get_by_text("Alterações salvas.")).to_be_visible()
    expect(page.get_by_text("Preço de venda não informado.")).to_have_count(0)
    shot(page, "05-product-detail")

    page.get_by_role("link", name="Painel", exact=True).click()
    expect(page.get_by_text("Saúde do catálogo")).to_be_visible()
    shot(page, "06-dashboard")

    page.get_by_role("link", name="Organização", exact=True).click()
    expect(page.get_by_text(EMAIL)).to_be_visible()
    shot(page, "07-organization")
    page.get_by_role("link", name="Histórico", exact=True).click()
    expect(page.get_by_text("cadastrou o produto FO-100")).to_be_visible()
    page.get_by_role("link", name="Anúncios em massa", exact=True).click()
    expect(page.get_by_role("button", name="Criar lote")).to_be_visible()
    shot(page, "08-bulk-list")

    page.get_by_role("button", name="Sair").click()
    page.wait_for_url("**/entrar/**")
    page.goto(BASE + "/catalogo/")
    page.wait_for_url("**/entrar/**")  # protected route without session
    page.get_by_label("E-mail").fill(EMAIL)
    page.get_by_label("Senha").fill("errada-errada")
    page.get_by_role("button", name="Entrar").click()
    expect(page.get_by_text("E-mail ou senha incorretos.")).to_be_visible()
    page.get_by_label("Senha").fill("senha-forte-123")
    page.get_by_role("button", name="Entrar").click()
    page.wait_for_url("**/catalogo/")  # returns where the user was going

    m = b.new_context(viewport={"width": 390, "height": 844}, storage_state=ctx.storage_state(), is_mobile=True, has_touch=True)
    mp = m.new_page()
    mp.goto(BASE + "/painel/")
    expect(mp.get_by_text("Saúde do catálogo")).to_be_visible()
    shot(mp, "09-mobile-dashboard")
    mp.get_by_role("button", name="Abrir menu").click()
    shot(mp, "10-mobile-menu")
    mp.get_by_role("link", name="Produtos", exact=True).click()
    mp.wait_for_url("**/catalogo/")
    overflow = mp.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    shot(mp, "11-mobile-catalog")
    b.close()

print("console errors:", console_errors)
print("mobile horizontal overflow:", overflow)
print("E2E OK")
