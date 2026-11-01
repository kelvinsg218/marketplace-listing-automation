"""E2E (Edge) of the official-sheet flow with a SYNTHETIC file that mirrors the real layout:
template upload -> mapping with official lists -> batch blocked by a required column -> Assistente de Correção
("- Marca" -> default value, this batch only) -> validation ok -> spreadsheet generated (nothing is published).
Usage: .venv/Scripts/python apps/web/e2e/official_flow.py <out_dir> <base_url> <official_like.xlsx>
"""
import pathlib
import sys
import uuid

from playwright.sync_api import expect, sync_playwright

OUT, BASE, XLSX = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
OUT.mkdir(parents=True, exist_ok=True)
EMAIL = f"oficial-{uuid.uuid4().hex[:6]}@example.com"
URL = "https://http2.mlstatic.com/D_NQ_NP_000000-MLA00000000000_000000-F.jpg"
errors = []
expect.set_options(timeout=60_000)  # next dev compiles pages on first visit


def shot(page, name):
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)


with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_context(viewport={"width": 1440, "height": 900}, locale="pt-BR").new_page()
    page.set_default_timeout(120_000)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE + "/cadastro/")
    page.get_by_label("Seu nome").fill("Operador Teste")
    page.get_by_label("Empresa").fill("Peças Demo E2E")
    page.get_by_label("E-mail").fill(EMAIL)
    page.get_by_label("Senha").fill("senha-forte-123")
    page.get_by_role("button", name="Criar conta").click()
    page.wait_for_url("**/painel/")

    page.goto(BASE + "/marketplaces/")
    page.get_by_label("Nome da conta").fill("Conta teste")
    page.get_by_role("button", name="Adicionar").click()
    expect(page.get_by_text("Conta adicionada.")).to_be_visible()

    page.goto(BASE + "/templates/")
    page.get_by_label("Conta que baixou a planilha").select_option(label="Conta teste")
    with page.expect_file_chooser() as fc:
        page.get_by_role("button", name="Escolher .xlsx").click()
    fc.value.set_files(XLSX)
    expect(page.get_by_text("Template registrado e inspecionado.")).to_be_visible()
    expect(page.get_by_text("Válido")).to_be_visible()  # deadline found + confirmed by the file itself
    page.get_by_role("link", name=pathlib.Path(XLSX).name).click()
    page.wait_for_url("**/templates/detalhe/**")
    page.get_by_label("Aba").select_option("Peças de Teste")
    expect(page.get_by_text("Mapeamento de atributos")).to_be_visible()
    for header, field in (("Título: informe o produto, marca, modelo e destaque as características principais", "name"),
                          ("Fotos", "photos"), ("SKU", "sku"), ("Estoque", "stock"), ("Preço [R$]", "price"),
                          ("Marca", "brand"), ("Número de peça", "sku")):
        page.get_by_label(f"Campo para {header}", exact=True).select_option(field)
    # Official list as a dropdown for the default value.
    expect(page.get_by_label("Valor padrão para Condição").locator("option", has_text="Usado")).to_have_count(1)
    page.get_by_role("button", name="Salvar mapeamento").click()
    expect(page.get_by_text("Mapeamento salvo.")).to_be_visible()
    shot(page, "40-template-mapping")

    page.goto(BASE + "/catalogo/?novo=1")
    dlg = page.get_by_role("dialog")
    dlg.get_by_label("SKU").fill("CM-001")
    dlg.get_by_label("Nome").fill("Cilindro mestre de freio")
    dlg.get_by_label("Preço de venda (R$)").fill("189,90")
    dlg.get_by_label("Estoque").fill("4")
    dlg.get_by_role("button", name="Salvar produto").click()
    expect(page.get_by_role("dialog")).to_have_count(0)
    page.get_by_role("link", name="Cilindro mestre de freio").click()
    page.wait_for_url("**/catalogo/produto/**")
    page.get_by_label("URLs do Gestor de fotos").fill(URL)
    page.get_by_role("button", name="Registrar URLs").click()
    expect(page.get_by_text("1 com URL oficial")).to_be_visible()

    page.goto(BASE + "/anuncios-em-massa/")
    page.get_by_placeholder("Ex.: Filtros — novembro").fill("Lote oficial E2E")
    page.get_by_role("button", name="Criar lote").click()
    page.wait_for_url("**/anuncios-em-massa/lote/**")
    batch_url = page.url
    nav = page.get_by_role("navigation", name="Etapas")
    nav.get_by_role("button", name="Conta").click()
    page.get_by_label("Conta de vendedor").select_option(label="Conta teste")
    nav.get_by_role("button", name="Template").click()
    page.get_by_role("radio").first.click()
    expect(page.get_by_role("radio").first).to_be_checked()
    page.get_by_label("Aba de categoria", exact=False).select_option("Peças de Teste")
    nav.get_by_role("button", name="Produtos").click()
    page.get_by_role("button", name="Adicionar todos do catálogo").click()
    expect(page.get_by_text("1 produto(s) no lote.")).to_be_visible()
    nav.get_by_role("button", name="Validar").click()
    page.get_by_role("button", name="Validar lote").click()
    nav.get_by_role("button", name="Corrigir").click()
    expect(page.get_by_text('"Marca" é obrigatório e está vazio.')).to_be_visible()
    shot(page, "41-blocked-by-template")

    page.goto(BASE + "/assistente/?lote=" + batch_url.split("id=")[1])
    page.get_by_label("Erro recebido").fill("- Marca")
    page.get_by_role("button", name="Analisar erro").click()
    page.get_by_role("button", name='Usar um valor padrão em "Marca" quando estiver vazio').click()
    page.get_by_label("Valor", exact=True).fill("Marca Demo")
    page.get_by_role("button", name="Simular antes e depois").click()
    expect(page.get_by_role("cell", name="Marca Demo")).to_be_visible()
    shot(page, "42-assistant-simulation")
    page.get_by_role("button", name="Aprovar").click()
    expect(page.get_by_text("regra criada")).to_be_visible()

    page.goto(batch_url)
    nav = page.get_by_role("navigation", name="Etapas")
    nav.get_by_role("button", name="Validar").click()
    page.get_by_role("button", name="Validar lote").click()
    expect(page.get_by_text("0 com erros", exact=False)).to_be_visible()
    nav.get_by_role("button", name="Revisar").click()
    expect(page.get_by_role("cell", name="Marca Demo")).to_be_visible()
    nav.get_by_role("button", name="Exportar").click()
    page.get_by_role("button", name="Validar e gerar planilha").click()
    expect(page.get_by_text("Planilha gerada: 1 linha(s), integridade verificada.")).to_be_visible()
    expect(page.get_by_role("link", name="Baixar XLSX para conferência")).to_be_visible()
    shot(page, "43-exported")

    page.goto(BASE + "/regras/")
    expect(page.get_by_text("Somente um lote")).to_be_visible()
    shot(page, "44-rules")
    browser.close()

print("page errors:", errors)
print("OFFICIAL E2E OK")
