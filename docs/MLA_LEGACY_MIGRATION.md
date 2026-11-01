# Do desktop para a web: preservação e migração

## Preservação

- O app desktop (`src/mla`, `tests/`, `tools/`, `installer/`, `mla.spec`) **continua onde está, funcionando e com
  release própria** (0.1.x-beta). Nada foi movido. Mover para `legacy/` quebraria o PyInstaller, o instalador e os
  caminhos de testes, sem ganho. Se um dia houver motivo, a mudança será um `git mv` dedicado, com build verificado.
- A web vive em `apps/`, com venv, dependências e testes próprios. Os dois não se importam.
- Dados reais do desktop (`%LOCALAPPDATA%\MLA`) **não são lidos nem migrados automaticamente.**

## Aproveitamento do legado

| Desktop | Destino web | Como |
|---|---|---|
| `core/validation.py`: `normalize_gtin`, `gtin_valid`, regras de SKU | `mla_api/domain/catalog.py` | **Copiado** (etapa B), com a origem anotada |
| `core/units.py` (centavos, gramas, mm; parsing BR) | `mla_api/domain/units.py` | Copiar na etapa C; sem dependência de Qt nem de SQLite |
| `importing/mapping.py` (dicionário de sinônimos, sugestão de colunas) | `mla_api/importing/` | Copiar na etapa C; é a base do mapeamento de templates na etapa D |
| `importing/readers.py` (CSV/XLSX/JSON/XML/PDF, XML sem DOCTYPE) | idem | Copiar; trocar caminhos locais por streams do storage |
| `importing/archive.py` (ZIP com lista permitida, sem executáveis nem links) | idem | Copiar; destino = área temporária por organização |
| `importing/values.py` (parsing de valores) | idem | Copiar; trocar a dependência de `services.compatibility` por uma interface |
| `importing/service.py` (analisar → planejar → decidir → gravar, savepoint por linha) | serviço + worker | **Reescrever** sobre PostgreSQL e fila; manter o desenho (D-014) |
| `services/listing_export.py` (neutraliza injeção de fórmula) | exportação | Reaproveitar a regra de neutralização |
| Proveniência de compatibilidades (D-016), histórico por campo (D-018), edição em lote (D-018) | catálogo web | Reimplementar com as mesmas regras |
| `integrations/mercadolivre.py` (OAuth + PKCE, atributos por categoria, validação sem publicar) | marketplaces (etapa D+) | Reaproveitar a lógica HTTP; os tokens passam do DPAPI para segredo cifrado por organização |

**Substituído, não migrado:** telas PySide6, `MainWindow`, diálogos, `ExecutionBridge`, SQLite local, empresas por
pasta (D-017 dá lugar a organizações + RLS), automação Playwright com o Edge (D-005; a web não automatiza formulários
como fluxo principal), atualizador e instalador.

**Por que copiar e não importar:** o pacote `mla` puxa PySide6 e Playwright como dependências do projeto. Importá-lo
na API levaria isso para o servidor. As cópias são pequenas e funções puras. Quando os dois lados precisarem evoluir
juntos, extrai-se um pacote `packages/mla_core` usado por ambos.

## Ferramenta de migração (quando for pedida)

Uma ferramenta explícita, nunca automática:
1. O usuário exporta pelo desktop (exportação de catálogo existente) ou aponta um backup `.db`.
2. `tools/migrate_desktop.py --source <arquivo> --org <id>` roda em **modo simulação** por padrão e gera um relatório
   (quantos produtos, conflitos de SKU, mídias ausentes).
3. Com `--apply`, grava como uma importação comum (lote com histórico, desfazível pela exclusão do lote) na organização
   escolhida.
4. O banco do desktop é aberto **somente leitura** e nunca é alterado.
