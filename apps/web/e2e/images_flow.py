"""E2E (Edge): Central de Imagens with fictitious data -> upload, Gestor URL, primary image, GTIN search, AI studio
state without a configured provider (must say so; nothing simulated).
Usage: .venv/Scripts/python apps/web/e2e/images_flow.py <out_dir> <base_url>
"""
import pathlib
import struct
import sys
import tempfile
import uuid
import zlib

from playwright.sync_api import expect, sync_playwright

OUT, BASE = pathlib.Path(sys.argv[1]), sys.argv[2]
OUT.mkdir(parents=True, exist_ok=True)
EMAIL = f"imagens-{uuid.uuid4().hex[:6]}@example.com"
URL = "https://http2.mlstatic.com/D_NQ_NP_000000-MLA00000000000_000000-F.jpg"
expect.set_options(timeout=60_000)


def png(path: pathlib.Path, w=120, h=120, color=(255, 101, 0)) -> pathlib.Path:
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = zlib.compress((b"\x00" + bytes(color) * w) * h, 9)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", raw) + chunk(b"IEND", b""))
    return path


image = png(pathlib.Path(tempfile.mkdtemp()) / "produto.png")
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_context(viewport={"width": 1440, "height": 900}, locale="pt-BR").new_page()
    page.set_default_timeout(120_000)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE + "/cadastro/")
    page.get_by_label("Seu nome").fill("Operador Imagens")
    page.get_by_label("Empresa").fill("Imagens Demo")
    page.get_by_label("E-mail").fill(EMAIL)
    page.get_by_label("Senha").fill("senha-forte-123")
    page.get_by_role("button", name="Criar conta").click()
    page.wait_for_url("**/painel/")
    page.goto(BASE + "/catalogo/?novo=1")
    dlg = page.get_by_role("dialog")
    dlg.get_by_label("SKU").fill("VASO-01")
    dlg.get_by_label("Nome").fill("Vaso decorativo laranja")
    dlg.get_by_label("GTIN / EAN").fill("7891234567895")
    dlg.get_by_role("button", name="Salvar produto").click()
    expect(page.get_by_role("dialog")).to_have_count(0)

    page.goto(BASE + "/fotos/")
    page.get_by_label("Buscar").fill("7891234567895")  # search by GTIN
    page.get_by_role("button", name="Vaso decorativo laranja").click()
    with page.expect_file_chooser() as fc:
        page.get_by_role("button", name="JPG, PNG ou WEBP").click()
    fc.value.set_files(str(image))
    expect(page.get_by_text("Imagem enviada.")).to_be_visible()
    expect(page.get_by_text("Arquivo no MLA")).to_be_visible()
    page.get_by_label("URLs do Gestor").fill(URL)
    page.get_by_role("button", name="Registrar").click()
    expect(page.get_by_text("URLs do Gestor registradas.")).to_be_visible()
    page.get_by_role("button", name="Ver imagem 2").click()
    page.get_by_role("button", name="Definir como principal").click()
    expect(page.get_by_text("Imagem principal definida.")).to_be_visible()
    expect(page.get_by_text("Nenhum provedor está configurado; nada é simulado.", exact=False)).to_be_visible()
    page.screenshot(path=str(OUT / "60-central-imagens.png"), full_page=True)
    browser.close()

print("page errors:", errors)
print("IMAGES E2E OK")
