# Desktop → Web: inventário e migração (concluída em 01/11/2026)

**Decisão (D-030):** o MLA Desktop foi descontinuado. O MLA Web 2.0 é o único produto do repositório. O código do
desktop fica preservado só no histórico do git (último commit com ele: `d3e1d67`). As alterações locais que nunca
tinham sido commitadas foram salvas em `local-archive/desktop-wip-2026-11-01/` (fora do git): um patch e `edition.py`.

## Auditoria de dependências

- `apps/api` e `apps/web` **não importavam nada** do pacote desktop `mla`: a busca por `from mla.` / `import mla` não
  encontrou ocorrências.
- O que a web usava do desktop já era cópia: a regra de GTIN, em `domain/catalog.py`.
- O único uso compartilhado era o **ambiente Python da raiz** (`.venv`), que dá o Playwright aos testes E2E. Agora as
  dependências deles estão em `apps/web/e2e/requirements.txt`.

## MANTER (usado diretamente pelo MLA Web)

| Item | Motivo |
|---|---|
| `apps/api`, `apps/web`, `infra/`, `docker-compose.yml` | Produto |
| `docs/MLA_*`, `CURRENT_STATUS`, `NEXT_STEPS`, `DECISIONS`, `TOOLS_INVENTORY` | Documentação viva (DECISIONS mantém D-001…D-020 como histórico) |
| `tools/logscan.py`, `tools/skills_catalog.py`, `tools/ollama_assist.py`, `tools/skills-catalog/` (python-patterns, writing-plans) | Ferramentas de desenvolvimento genéricas |
| `.claude/skills/` (frontend-design, python-testing, systematic-debugging, TDD, verification, webapp-testing, strategic-compact), `.mcp.json` | Ferramentas de sessão, não ligadas ao desktop |

## MIGRAR (lógica útil extraída para a API, sem PySide6, SQLite ou UI)

| Origem (desktop) | Destino (web) | Observação |
|---|---|---|
| `core/units.py` | `mla_api/importing/units.py` | Dinheiro (centavos) e medidas, formato brasileiro |
| `importing/mapping.py` | `mla_api/importing/mapping.py` | Dicionário de sinônimos de colunas e sugestão de mapeamento |
| `importing/readers.py` | `mla_api/importing/readers.py` | CSV (detecção de codificação), XLSX (sem macros), JSON, XML (sem DOCTYPE/ENTITY), PDF (texto, sem OCR) |
| `importing/archive.py` | `mla_api/importing/archive.py` | Extração de ZIP com lista permitida (sem executáveis, scripts, links ou caminhos para fora) |
| `importing/values.py` | `mla_api/importing/values.py` | Parsing e validação de valores por linha |
| `services/compatibility.py` (só o parsing de anos) | `mla_api/importing/compatibility.py` | "2010-2015", "até 2014", "2018+" |
| `services/images.py` (só a leitura de cabeçalho) | `mla_api/domain/image_info.py` | Formato e dimensões de JPG/PNG/WEBP sem Pillow, também a partir de bytes |
| `core/validation.py` (GTIN, SKU) | `mla_api/domain/catalog.py` | Já migrado na etapa B |
| Testes puros de `tests/unit/test_imports.py` e `test_units.py` | `apps/api/tests/test_import_parsers.py`, `test_units.py` | 25 testes migrados + 6 novos (cabeçalhos de imagem sem Qt, anos) |

**Não migrado agora, a reconstruir na web quando necessário** (o desenho está nas decisões do desktop e no histórico
do git):

| Item | Por quê | Onde reconstruir |
|---|---|---|
| Serviço de importação (analisar → planejar → decidir → gravar, D-014) | Ligado ao SQLite e a threads do desktop | Etapa C, sobre PostgreSQL + fila; usará `mla_api/importing` |
| Compatibilidades (repositório, origem/verificação, D-016) | Tabelas do desktop | Etapa C: tabela por organização + RLS |
| Histórico por campo (`core/changes.py`, D-018) e edição em lote | Ligado ao modelo do desktop | Etapa C |
| Cliente da API do Mercado Livre (`integrations/mercadolivre.py`: OAuth + PKCE, atributos, validação sem publicar; inclui as alterações locais não commitadas, no patch arquivado) | Tokens via DPAPI do Windows e uso síncrono | Adaptador da API oficial (estratégia B), com tokens cifrados por organização |
| Exportação intermediária (`services/listing_export.py`) | Substituída pelo writer oficial | — |

## REMOVER (exclusivo do desktop)

| Item | Conteúdo |
|---|---|
| `src/mla/` (168 arquivos) | UI PySide6 (janelas, páginas, widgets, tema), automação Playwright com o Edge local (fila, executor, adaptadores, simulador), persistência SQLite e migrações, licenciamento, empresas por pasta, atualizador, diagnóstico, recursos (ícones, fontes, marketplace simulado) |
| `tests/` (27 arquivos) | Testes de UI, automação, persistência e serviços do desktop (os puros foram migrados) |
| `pyproject.toml` da raiz, `mla.spec`, `installer/` | Pacote desktop (PySide6, Playwright, PyInstaller), especificação do executável, instalador e desinstalador, notas de release |
| `demo/` | Roteiro de demonstração do desktop (as saídas locais ignoradas continuam no disco) |
| `tools/build_release.py`, `make_icon.py`, `ui_snapshots.py` | Build e capturas do desktop |
| Skills `pyside6-design` (ativa), `windows-desktop-e2e`, `generating-python-installer` (dormentes) | Específicas de Qt/instalador |
| Documentos do desktop | ARCHITECTURE, AUDITORIA_MVP, BUILD_E_DISTRIBUICAO, COMMERCIAL_ROADMAP, DEMO_COMERCIAL, DEMO_TEST_REPORT, DEVELOPMENT, INSTALLATION, PROGRESSO_MVP, PROJECT_CONTEXT, ROTEIRO_TESTE_SEGUNDO_COMPUTADOR, TESTING, USER_GUIDE, `docs/comercial/` |

**Arquivados em `docs/archive/`** (histórico útil): o guia de criação do aplicativo no portal de desenvolvedores do
ML (servirá para o OAuth da web), o plano SaaS e o changelog do desktop.

**Não tocados (locais, fora do git):**
- `build/` e `dist/` (1,4 GB de builds antigos; podem ser apagados à mão);
- o `.venv` da raiz;
- os dados do desktop em `%LOCALAPPDATA%\MLA`;
- o banco de desenvolvimento da web em `apps/api/.data/`.
