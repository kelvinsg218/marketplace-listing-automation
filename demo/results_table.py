"""Turn demo/output/demo-results.json into Markdown tables for docs/DEMO_TEST_REPORT.md."""
import json
import sys
from collections import OrderedDict
from pathlib import Path

KINDS = {"ok": "Sucesso", "fail": "Falha", "skip": "Não executado", "bug": "Bug encontrado", "note": "Observação"}

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
sections: "OrderedDict[str, list]" = OrderedDict()
for item in data["items"]:
    sections.setdefault(item["section"] or "Geral", []).append(item)
counts = {k: sum(1 for i in data["items"] if i["kind"] == k) for k in KINDS}
print(f"Início: {data['started']}  |  " + ", ".join(f"{KINDS[k]}: {n}" for k, n in counts.items()))
for section, items in sections.items():
    print(f"\n#### {section}\n")
    print("| Resultado | Verificação | Detalhe |")
    print("|---|---|---|")
    for i in items:
        detail = i["detail"].replace("|", "/").replace("\n", " ")[:220]
        print(f"| {KINDS[i['kind']]} | {i['name'].replace('|', '/')} | {detail} |")
