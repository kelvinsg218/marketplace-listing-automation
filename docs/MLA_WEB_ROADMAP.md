# MLA Web 2.0: roteiro

Versionamento: o desktop segue `0.1.x-beta` (`pyproject.toml` da raiz). A web começa em **`2.0.0-alpha.0`**
(`apps/api/pyproject.toml` e `apps/web/package.json`), linha independente. Sobe para `2.0.0-beta` na etapa F.

## Etapas

| Etapa | Escopo | Situação |
|---|---|---|
| **A** Discovery e arquitetura | Pesquisa ML, auditoria do legado, arquitetura, design system, plano | **Concluída, com bloqueio:** documentações oficiais inacessíveis (403) e templates não analisados |
| **B** Fundação web | FastAPI, PostgreSQL/Alembic, autenticação, organizações e membros, permissões, auditoria, layout, painel, catálogo básico | **Concluída** (commit `dcc16fe`). Pendente: RLS em PostgreSQL real e compose executado |
| **C** Catálogo e importações | Variações, mídias, arquivos, compatibilidades, histórico por campo, edição em lote, Central de Importações, fila e worker | **Em andamento:** variações e Central de Fotos implementadas. Importações, compatibilidades, fila e worker pendentes |
| **D** Mercado Livre | Templates oficiais, inspeção, mapeamento, validação, wizard de anúncios em massa, exportação XLSX | **Em andamento:** registro, inspetor, prazo, mapeamento, validação com fontes, revisão e wizard de 12 etapas implementados. **Writer bloqueado** até chegar um XLSX real |
| **E** Lotes e resultados | Estados do lote, histórico, reprocessamento, importação da planilha de resultado | Planejada (depende de D e da planilha de erros real) |
| **F** Consolidação | SMTP, convites, configurações, limitador compartilhado, backups, observabilidade, deploy, testes de carga em PostgreSQL | Planejada |

## Critérios de aceitação

**B (fundação)**, cumprida exceto o que está marcado:
- [x] Cadastro, login, logout, sessão expirável, redefinição de senha com token de uso único
- [x] Papéis owner/admin/editor/viewer aplicados no backend; última pessoa proprietária protegida
- [x] Nenhuma rota de organização responde a não-membro (404) e nenhum id de outra organização é acessível
- [x] Auditoria de ações sensíveis, sem segredos
- [x] Painel com métricas reais e módulos inexistentes sinalizados
- [x] Layout responsivo sem rolagem horizontal em 390 px; fluxo E2E no Edge
- [ ] Teste de RLS executado em PostgreSQL (`pytest -m postgres` com `MLA_TEST_DATABASE_URL`)
- [ ] `docker compose up` executado do zero

**C:** importar CSV/XLSX de 5.000 produtos em segundo plano sem travar a UI; cancelamento sem gravação parcial;
relatório de inconsistências; ZIP com path traversal, executáveis e links recusado; job de uma organização nunca
lê dado de outra (teste); volumes 10/100/1.000/5.000 medidos em PostgreSQL.

**D:** um template real de cada categoria analisada é lido sem perda (abas, validações e ocultas preservadas); o
arquivo exportado é uma cópia do original com só as células de dados alteradas (teste comparando o XML interno);
nenhum obrigatório inventado; a planilha gerada é **aceita no Anunciador em Massa real**, com evidência registrada.

**E:** estados só avançam para "Enviado externamente" ou "Resultado recebido" por confirmação ou planilha de
resultado importada; as linhas rejeitadas voltam para correção.

**D (parcial, cumprido nesta sessão):**
- [x] Template ligado à organização e à conta de vendedor; o original nunca é alterado (teste de hash e de download byte a byte)
- [x] Inspetor sem efeitos colaterais; arquivos perigosos recusados ou sinalizados; prazo com ano deduzido marcado
- [x] Template de outra conta recusado no lote (P1 p.8); prazo vencido bloqueia
- [x] Validação separa interna, documentação, template e hipótese; limite de 10.000 linhas por dia (P1 p.8)
- [x] Estados "enviado" e "resultado" só com confirmação; exportar responde 409 enquanto o writer não existe
- [ ] Writer sobre template real · [ ] Error Importer sobre planilha de retorno real · [ ] aceite real no Anunciador em massa

## Próxima entrega (sugerida)

1. Você fornece o conteúdo das duas páginas e 2 ou 3 templates (lista em MLA_MERCADOLIVRE_RESEARCH.md §5).
2. Em paralelo, a etapa C começa: variações, mídias com upload autorizado, unidades, Central de Importações (CSV/XLSX
   primeiro) com worker em fila PostgreSQL.
3. Com os templates em mãos: inspetor de templates (somente leitura) e seção "Estrutura confirmada" na pesquisa,
   antes de qualquer exportação.

## Como executar

```powershell
# API (porta 8000)
cd apps\api
py -3.13 -m venv .venv; .venv\Scripts\python -m pip install -e ".[dev]"
copy .env.example .env
.venv\Scripts\python -m alembic upgrade head
$env:PYTHONPATH="src"; .venv\Scripts\python -m uvicorn mla_api.asgi:app --reload

# Frontend (porta 3000, faz proxy de /api para a 8000)
cd apps\web
npm install; npm run dev
```

Produção local em origem única: `npm run build` em `apps/web` e depois `MLA_WEB_DIST_DIR=../web/out` no `.env` da API.
Abra http://localhost:8000.

Com Docker: `docker compose up --build` (ainda não executado).

## Como testar

```powershell
cd apps\api; .venv\Scripts\python -m pytest              # 86 testes; RLS fica "skipped" sem PostgreSQL
.venv\Scripts\python -m pytest -m perf -s                 # cenários 10/100/1.000/5.000
$env:MLA_TEST_DATABASE_URL="postgresql+psycopg://mla:mla-dev-password@localhost:5432/mla_test"; .venv\Scripts\python -m pytest -m postgres
cd ..\web; npm run typecheck; npm run build
```

E2E de navegador (cadastro → painel → produtos → validação → edição → membros → histórico → logout/login →
celular 390 px), com a API servindo o build estático e um banco de desenvolvimento:
`.venv\Scripts\python apps\web\e2e\smoke_flow.py <pasta_capturas> http://127.0.0.1:8000` (venv do desktop, que já
tem Playwright e usa o Edge). Gera as capturas usadas na revisão visual.

Fluxo de anúncios em massa no Edge, com template **sintético** (não oficial):
`.venv\Scripts\python apps\web\e2e\bulk_flow.py <pasta_capturas> http://127.0.0.1:8000 <arquivo.xlsx>`. Gere o arquivo com `build()` de `apps/api/tests/synthetic_template.py`.
