"""E2E of the bulk-listing flow through Edge: seller account, template upload + inspection, deadline, mapping,
product with variations and Gestor URLs, batch wizard (validate, fix, review) and the blocked export.

Uses a SYNTHETIC workbook (apps/api/tests/synthetic_template.py), never an official template, and a development
database only:  .venv/Scripts/python apps/web/e2e/bulk_flow.py <screenshot_dir> <base_url> <synthetic.xlsx>
"""
import pathlib
import sys
import uuid

from playwright.sync_api import expect, sync_playwright

OUT, BASE, XLSX = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
OUT.mkdir(parents=True, exist_ok=True)
EMAIL = f"bulk-{uuid.uuid4().hex[:6]}@example.com"
URLS = ("https://http2.mlstatic.com/D_NQ_NP_903478-MLM72199717417_102023-F.jpg,"
        "https://http2.mlstatic.com/D_NQ_NP_929525-MLM72199413355_102023-F.jpg")
errors = []


def shot(page, name):
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)


with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_context(viewport={"width": 1440, "height": 900}, locale="pt-BR").new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.goto(BASE + "/cadastro/")
    page.get_by_label("Seu nome").fill("Ana Operadora")
    page.get_by_label("Empresa").fill("Biscoitos Demo")
    page.get_by_label("E-mail").fill(EMAIL)
    page.get_by_label("Senha").fill("senha-forte-123")
    page.get_by_role("button", name="Criar conta").click()
    page.wait_for_url("**/painel/")

    # Seller account
    page.get_by_role("link", name="Marketplaces", exact=True).click()
    page.get_by_label("Nome da conta").fill("Conta principal")
    page.get_by_role("button", name="Adicionar").click()
    expect(page.get_by_text("Conta adicionada.")).to_be_visible()
    shot(page, "20-marketplaces")

    # Template upload + inspection
    page.get_by_role("link", name="Templates", exact=True).click()
    page.get_by_label("Conta que baixou a planilha").select_option(label="Conta principal")
    with page.expect_file_chooser() as fc:
        page.get_by_role("button", name="Escolher .xlsx").click()
    fc.value.set_files(XLSX)
    expect(page.get_by_text("Template registrado e inspecionado.")).to_be_visible()
    expect(page.get_by_text("Prazo a confirmar").or_(page.get_by_text("Prazo vencido"))).to_be_visible()
    shot(page, "21-templates")
    page.get_by_role("link", name="sintetico-biscoitos.xlsx").click()
    page.wait_for_url("**/templates/detalhe/**")
    expect(page.get_by_text("Mapeamento de atributos")).to_be_visible()
    page.get_by_label("Informar data limite").fill("2099-12-31")
    page.get_by_role("button", name="Salvar data").click()
    expect(page.get_by_text("confirmada")).to_be_visible()
    page.get_by_label("Linha de cabeçalho").select_option("3")
    expect(page.get_by_label("Campo para Fotos")).to_have_value("photos")  # suggestion, not yet saved
    page.get_by_label("Campo para Título").select_option("name")
    page.get_by_role("button", name="Salvar mapeamento").click()
    expect(page.get_by_text("Mapeamento salvo.")).to_be_visible()
    expect(page.get_by_text("confirmada", exact=True).nth(1)).to_be_visible()  # header row now confirmed
    shot(page, "22-template-detail")

    # Product with variation and official photo URLs
    page.get_by_role("link", name="Produtos", exact=True).click()
    page.get_by_role("button", name="Novo produto").click()
    dlg = page.get_by_role("dialog")
    dlg.get_by_label("SKU").fill("BIS-1")
    dlg.get_by_label("Nome").fill("Biscoito amanteigado 200 g")
    dlg.get_by_label("Marca").fill("Demo")
    dlg.get_by_label("Preço de venda (R$)").fill("7,90")
    dlg.get_by_label("Estoque").fill("40")
    dlg.get_by_role("button", name="Salvar produto").click()
    expect(page.get_by_role("dialog")).to_have_count(0)
    page.get_by_role("button", name="Novo produto").click()
    dlg = page.get_by_role("dialog")
    dlg.get_by_label("SKU").fill("BIS-2")
    dlg.get_by_label("Nome").fill("Biscoito sem preço")
    dlg.get_by_role("button", name="Salvar produto").click()
    expect(page.get_by_role("dialog")).to_have_count(0)
    page.get_by_role("link", name="Biscoito amanteigado 200 g").click()
    page.wait_for_url("**/catalogo/produto/**")
    page.get_by_label("SKU da variação").fill("BIS-1-CHOC")
    page.get_by_label("Atributos").fill("Sabor=Chocolate")
    page.get_by_role("button", name="Adicionar").click()
    expect(page.get_by_text("Sabor: Chocolate")).to_be_visible()
    page.get_by_label("URLs do Gestor de fotos").fill(URLS)
    page.get_by_role("button", name="Registrar URLs").click()
    expect(page.get_by_text("2 com URL oficial")).to_be_visible()
    shot(page, "23-product-variants-photos")

    page.get_by_role("link", name="Central de Imagens", exact=True).click()
    expect(page.get_by_text("sem imagem aprovada").first).to_be_visible()  # BIS-2 has no photo
    shot(page, "24-photos")

    # Batch wizard
    page.get_by_role("link", name="Anúncios em massa", exact=True).click()
    page.get_by_placeholder("Ex.: Filtros — novembro").fill("Biscoitos — novembro")
    page.get_by_role("button", name="Criar lote").click()
    page.wait_for_url("**/anuncios-em-massa/lote/**")
    nav = page.get_by_role("navigation", name="Etapas")
    nav.get_by_role("button", name="Conta e marketplace").click()
    page.get_by_label("Conta de vendedor").select_option(label="Conta principal")
    nav.get_by_role("button", name="Preparação").click()
    page.get_by_role("radio").first.click()
    expect(page.get_by_role("radio").first).to_be_checked()  # set from the server response
    page.get_by_label("Aba de categoria", exact=False).select_option("Biscoitos")
    nav.get_by_role("button", name="Produtos").click()
    page.get_by_role("button", name="Adicionar todos do catálogo").click()
    expect(page.get_by_text("2 produto(s) no lote.")).to_be_visible()
    nav.get_by_role("button", name="Preparação").click()
    expect(page.get_by_text("Cabeçalho confirmado (linha 3)")).to_be_visible()
    nav.get_by_role("button", name="Revisão").click()
    page.get_by_role("button", name="Validar lote").click()
    expect(page.get_by_text("com erros", exact=False).first).to_be_visible()
    shot(page, "25-wizard-validate")
    nav.get_by_role("button", name="Revisão").click()
    expect(page.get_by_text("Preço de venda não informado.")).to_be_visible()
    expect(page.get_by_text("Regra interna").first).to_be_visible()
    shot(page, "26-wizard-fix")
    nav.get_by_role("button", name="Revisão").click()
    expect(page.get_by_text("BIS-1-CHOC")).to_be_visible()
    shot(page, "27-wizard-review")
    nav.get_by_role("button", name="Exportação e publicação").click()
    expect(page.get_by_text("não tem a estrutura oficial reconhecida", exact=False).first).to_be_visible()
    nav.get_by_role("button", name="Exportação e publicação").click()
    expect(page.get_by_role("button", name="Confirmo que enviei a planilha")).to_be_disabled()
    shot(page, "28-wizard-send")

    m = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                            storage_state=page.context.storage_state()).new_page()
    m.goto(page.url)
    expect(m.get_by_role("navigation", name="Etapas")).to_be_visible()
    overflow = m.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    shot(m, "29-wizard-mobile")
    browser.close()

print("page errors:", errors)
print("mobile horizontal overflow:", overflow)
print("BULK E2E OK")
