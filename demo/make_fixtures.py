"""Fictitious demo bases for the MLA demonstration (company "Horizonte Autopeças", all data invented).

Writes into demo/fixtures/: CSV (Windows-1252, ';'), XLSX (cover sheet + data), JSON (nested), XML, PDF (table),
ZIP (sheet + photos + a blocked .bat), a photo folder named by SKU, compatibility CSVs and a large CSV used to
demonstrate cancelling an import. Images are drawn with Qt (no external files).
"""
from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter


def gtin13(body12: str) -> str:
    digits = [int(c) for c in body12]
    total = sum(d * (3 if i % 2 else 1) for i, d in enumerate(digits))
    return body12 + str((10 - total % 10) % 10)


def product_image(path: Path, sku: str, label: str, hue: int, variant: int = 0) -> Path:
    img = QImage(900, 900, QImage.Format.Format_RGB32)
    painter = QPainter(img)
    grad = QLinearGradient(QPointF(0, 0), QPointF(900, 900))
    grad.setColorAt(0, QColor.fromHsv(hue, 30, 240))
    grad.setColorAt(1, QColor.fromHsv(hue, 80, 175))
    painter.fillRect(img.rect(), grad)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor.fromHsv((hue + 180) % 360, 110, 90 + variant * 40))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(QRectF(230, 220 + variant * 20, 440, 400), 48, 48)
    painter.setPen(QColor(255, 255, 255))
    font = QFont("Segoe UI", 34, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(QRectF(0, 660, 900, 70), Qt.AlignmentFlag.AlignCenter, sku)
    font.setPointSize(20)
    font.setWeight(QFont.Weight.Normal)
    painter.setFont(font)
    painter.drawText(QRectF(0, 735, 900, 60), Qt.AlignmentFlag.AlignCenter, label)
    painter.drawText(QRectF(0, 40, 900, 50), Qt.AlignmentFlag.AlignCenter, "imagem fictícia de demonstração")
    painter.end()
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(path), quality=88)
    return path


def make_pdf(path: Path, lines: list[tuple[int, int, str]]) -> Path:
    def escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    stream = "\n".join(f"BT /F1 10 Tf {x} {y} Td ({escape(t)}) Tj ET" for x, y, t in lines).encode("cp1252")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >>"
        b" /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    path.write_bytes(bytes(out))
    return path


DESC = ("{name} da linha Horizonte, produto fictício criado para a demonstração do MLA. Material resistente, "
        "acabamento de fábrica e embalagem individual com etiqueta de identificação.")

# sku, name, title, category, price, stock, brand, weight kg, dims cm (c, l, a), hue
CSV_ROWS = [
    ("HZ-FIL-01", "Filtro de óleo", "Filtro de óleo motor 1.0 linha Horizonte", "Acessórios", "29,90", 40, 0.30, (12, 10, 10), 30),
    ("HZ-PAS-02", "Pastilha de freio dianteira", "Pastilha de freio dianteira cerâmica Horizonte", "Acessórios", "119,00", 12, 0.90, (18, 12, 6), 0),
    ("HZ-VEL-03", "Jogo de velas de ignição", "Jogo com 4 velas de ignição Horizonte", "Acessórios", "89,50", 25, 0.25, (14, 9, 4), 200),
    ("HZ-PAL-04", "Palheta limpador 22 pol", "Palheta limpador de para-brisa 22 polegadas", "Acessórios", "39,90", 60, 0.20, (60, 6, 4), 260),
    ("HZ-LAM-05", "Lâmpada H4 halógena", "Lâmpada H4 halógena 60/55W Horizonte", "Acessórios", "24,90", 80, 0.10, (10, 6, 6), 50),
    ("HZ-TAP-06", "Tapete automotivo borracha", "Jogo de tapetes automotivos em borracha 4 peças", "Acessórios", "149,90", 15, 2.10, (70, 50, 5), 120),
]


def build(root: Path) -> dict[str, Path]:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    paths: dict[str, Path] = {}

    # 1) CSV exported by an ERP (Windows-1252, ';'), photos next to it; one duplicate and one bad price
    base = root / "erp-csv"
    lines = ["codigo;descricao;titulo;descricao_completa;categoria;preco_venda;saldo;marca;ean;peso_kg;comprimento;"
             "largura;altura;foto"]
    for n, (sku, name, title, category, price, stock, weight, dims, hue) in enumerate(CSV_ROWS):
        ean = gtin13(f"789{n + 1:09d}")
        photo = "" if sku == "HZ-PAL-04" else f"fotos/{sku}.jpg"
        if sku == "HZ-LAM-05":
            photo = "fotos/HZ-LAM-05-frente.jpg"  # referenced but missing: becomes pending media
        if sku not in ("HZ-LAM-05",):
            product_image(base / "fotos" / f"{sku}.jpg", sku, name, hue)
        lines.append(";".join([sku, name, title, DESC.format(name=name), category, price, str(stock), "Horizonte",
                               ean, f"{weight:.2f}".replace(".", ","), *(str(d) for d in dims), photo]))
    product_image(base / "fotos" / "HZ-PAS-02_2.jpg", "HZ-PAS-02", "Pastilha (verso)", 0, 1)
    lines.append("HZ-FIL-01;Filtro de óleo (linha repetida);Filtro;Linha repetida no arquivo;Acessórios;29,90;1;"
                 "Horizonte;;0,3;12;10;10;")
    lines.append("HZ-AMO-07;Amortecedor dianteiro;Amortecedor dianteiro Horizonte;Amortecedor;Acessórios;abc;3;"
                 "Horizonte;;3,2;55;12;12;")
    paths["csv"] = base / "produtos-erp.csv"
    paths["csv"].write_text("\n".join(lines) + "\n", encoding="cp1252")

    # 2) XLSX with a cover sheet and price/stock updates (+ one new product)
    from openpyxl import Workbook
    wb = Workbook()
    wb.active.title = "Capa"
    wb.active["A1"] = "Atualização de preços (dados fictícios)"
    ws = wb.create_sheet("Produtos")
    ws.append(["SKU", "Nome do produto", "Preço", "Estoque"])
    ws.append(["HZ-FIL-01", "Filtro de óleo", 31.5, 55])
    ws.append(["HZ-VEL-03", "Jogo de velas de ignição", 92.9, 25])
    ws.append(["HZ-TAP-06", "Tapete automotivo borracha", 139.9, 9])
    ws.append(["HZ-CAP-08", "Capa protetora para carro", 189.0, 7])
    paths["xlsx"] = root / "atualizacao-precos.xlsx"
    wb.save(paths["xlsx"])

    # 3) JSON from a supplier feed (nested)
    feed = {"fornecedor": "Distribuidora Sul (fictícia)", "dados": {"itens": [
        {"sku": "HZ-ORG-09", "nome": "Organizador de porta-malas", "preco": "79,90", "estoque": 20,
         "fabricante": {"marca": "Horizonte"}, "fotos": ["HZ-ORG-09.jpg"]},
        {"sku": "HZ-SUP-10", "nome": "Suporte veicular para celular", "preco": 59.9, "estoque": 33,
         "fabricante": {"marca": "Horizonte"}, "fotos": ["HZ-SUP-10.jpg"]}]}}
    paths["json"] = root / "fornecedor-json" / "feed-fornecedor.json"
    paths["json"].parent.mkdir(parents=True, exist_ok=True)
    paths["json"].write_text(json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8")

    # 4) XML from a partner catalog
    xml = ("<?xml version='1.0' encoding='utf-8'?><catalogo><produtos>"
           "<produto codigo_sku='HZ-CAB-11'><nome>Cabo de bateria auxiliar</nome><preco>99,90</preco>"
           "<estoque>14</estoque><marca>Horizonte</marca></produto>"
           "<produto codigo_sku='HZ-CAR-12'><nome>Carregador veicular USB-C</nome><preco>49,90</preco>"
           "<estoque>45</estoque><marca>Horizonte</marca></produto></produtos></catalogo>")
    paths["xml"] = root / "catalogo-parceiro.xml"
    paths["xml"].write_text(xml, encoding="utf-8")

    # 5) PDF price table (one row with an empty cell needs review)
    rows = [("Código", "Descrição", "Preço", "Estoque"), ("HZ-KIT-13", "Kit primeiros socorros", "69,90", "18"),
            ("HZ-EXT-14", "Extintor veicular ABC", "129,00", "6"), ("HZ-TRI-15", "Triângulo de segurança", "34,90", "")]
    pdf_lines = [(50, 800, "Tabela de preços (fictícia) Horizonte Autopeças")]
    y = 760
    for row in rows:
        pdf_lines += [(x, y, cell) for x, cell in zip((50, 150, 380, 470), row) if cell]
        y -= 18
    paths["pdf"] = make_pdf(root / "tabela-fornecedor.pdf", pdf_lines)

    # 6) ZIP: sheet + photos + a script that must never be extracted
    zroot = root / "zip-src"
    product_image(zroot / "fotos" / "HZ-ALA-16.jpg", "HZ-ALA-16", "Alarme automotivo", 280)
    paths["zip"] = root / "pacote-loja.zip"
    with zipfile.ZipFile(paths["zip"], "w") as zf:
        zf.writestr("produtos.csv", "sku;nome;titulo;preco;estoque;marca;imagem\n"
                                    "HZ-ALA-16;Alarme automotivo;Alarme automotivo com 2 controles;249,00;5;Horizonte;"
                                    "fotos/HZ-ALA-16.jpg\n")
        zf.write(zroot / "fotos" / "HZ-ALA-16.jpg", "fotos/HZ-ALA-16.jpg")
        zf.writestr("instalar.bat", "echo este arquivo nunca deve ser executado\n")

    # 7) photo folder named by SKU (resolves the pending image and adds photos to the JSON products)
    folder = root / "fotos-por-sku"
    product_image(folder / "HZ-LAM-05-frente.jpg", "HZ-LAM-05", "Lâmpada H4", 50)
    product_image(folder / "HZ-ORG-09.jpg", "HZ-ORG-09", "Organizador", 90)
    product_image(folder / "HZ-SUP-10_1.jpg", "HZ-SUP-10", "Suporte celular", 170)
    paths["folder"] = folder

    # 8) compatibility tables (client data, then an external source)
    paths["compat"] = root / "aplicacoes-cliente.csv"
    paths["compat"].write_text("sku;montadora;modelo;motor;anos;codigo_oem\n"
                               "HZ-PAS-02;Fiat;Uno;1.0 Fire;2010-2015;OEM-7712\n"
                               "HZ-PAS-02;Fiat;Palio;1.0;2012-2017;OEM-7712\n"
                               "HZ-PAS-02;Volkswagen;Gol;1.6;2013 a 2018;\n"
                               "HZ-FIL-01;Chevrolet;Onix;1.0;2016+;\n"
                               "HZ-FIL-01;Chevrolet;Onix;1.0;2016+;\n"
                               "HZ-XXX-99;Ford;Ka;1.0;2015;\n", encoding="utf-8")
    paths["compat_ext"] = root / "aplicacoes-site-fabricante.csv"
    paths["compat_ext"].write_text("sku;marca;modelo;anos\nHZ-PAL-04;Renault;Sandero;2014-2020\n"
                                   "HZ-PAL-04;Hyundai;HB20;2013-2019\n", encoding="utf-8")

    # 9) large base used to show cancelling a commit (nothing is written)
    big = ["sku;nome;titulo;preco;estoque;marca"]
    big += [f"GRD-{n:05d};Item de teste {n};Item de teste {n};{10 + n % 90},90;{n % 7};Horizonte" for n in range(3000)]
    paths["big"] = root / "base-grande.csv"
    paths["big"].write_text("\n".join(big) + "\n", encoding="utf-8")

    # 10) images for the product typed by hand in the editor
    paths["manual_imgs"] = root / "fotos-cadastro-manual"
    product_image(paths["manual_imgs"] / "HZ-SUP-20-a.jpg", "HZ-SUP-20", "Suporte magnético", 300)
    product_image(paths["manual_imgs"] / "HZ-SUP-20-b.jpg", "HZ-SUP-20", "Suporte magnético (lado)", 300, 1)
    return paths


if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    out = build(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "fixtures")
    for key, value in out.items():
        print(key, value)
