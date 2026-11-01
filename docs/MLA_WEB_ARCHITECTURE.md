# MLA Web 2.0: arquitetura

Situação em 01/11/2026: **etapa B concluída e publicada** (commit `dcc16fe`). Da etapa C: variações e fotos.
Da etapa D: registro e inspeção de templates, mapeamento, validação e o fluxo guiado de lotes. Tudo testado com
arquivos **sintéticos**. O preenchimento da planilha (writer) e o importador de erros esperam arquivos reais.

## 1. Visão geral

```
Navegador ──HTTPS──▶ [ nginx / FastAPI ]
                      ├── /            arquivos estáticos do Next.js (apps/web/out)
                      └── /api/*       FastAPI (apps/api) ──▶ PostgreSQL (RLS por organização)
                                              │
                                              ├──▶ Storage (local hoje; S3-compatível depois), chaves orgs/<org_id>/...
                                              └──▶ Worker (etapa C): fila em tabela PostgreSQL, SKIP LOCKED
```

Mesma origem para página e API: o cookie de sessão é `HttpOnly; SameSite=Lax`, sem CORS em produção e sem token
guardado em JavaScript.

## 2. Stack escolhida e por quê

| Camada | Escolha | Motivo | Alternativas descartadas |
|---|---|---|---|
| Frontend | **Next.js 15 (App Router) + React 19 + TypeScript + Tailwind 4**, exportado como **estático** | Sua preferência. O export estático elimina o servidor Node em produção: o app inteiro fica atrás de login, então SSR e SEO não trazem ganho. O deploy fica com um contêiner a menos e a autenticação fica numa origem só | Vite + React Router: equivalente tecnicamente; mantive Next pela preferência e pelo ecossistema. Next com SSR: dois servidores e cookies entre eles sem benefício |
| Ícones | lucide-react | Traço fino e consistente, tree-shaking | — |
| Gráficos | **nenhuma lib por enquanto** | Os dados de hoje cabem em barras CSS acessíveis. Recharts entra quando houver série temporal de verdade (lotes por semana etc.) | Recharts/Chart.js agora: dependência sem uso |
| Backend | **FastAPI + Pydantic 2 + SQLAlchemy 2 + Alembic** | Python reaproveita as regras do desktop (importadores, unidades, GTIN, mapeamento). openpyxl é Python | Node/Nest: perderia o código de importação já testado |
| Banco | **PostgreSQL 17** (SQLite só em desenvolvimento e testes) | RLS para isolamento, JSONB, concorrência | MySQL: RLS fraco |
| Senhas | Argon2id (argon2-cffi) | Padrão OWASP atual | bcrypt |
| Tarefas longas | **fila em tabela PostgreSQL** (`SELECT ... FOR UPDATE SKIP LOCKED`) + processo worker (etapa C) | Sem Redis/Celery: um serviço a menos para operar. Escala bem até milhares de jobs por hora | Celery + Redis: fica para quando houver volume que justifique |
| Infra dev | Docker Compose (db, api, web) | — | — |

**Restrição deste computador:** Docker e PostgreSQL não estão instalados, e não existe PostgreSQL embutido via pip
para Windows. Por isso a API aceita SQLite **fora de produção** (`Settings` recusa SQLite e cookie sem `Secure` em
`production`). O `docker-compose.yml` foi escrito, mas **ainda não foi executado**.

## 3. Estrutura do repositório

```
src/mla/, tests/, tools/, installer/   app desktop (legado funcional, intocado)
apps/api/                              FastAPI: src/mla_api, migrations/ (Alembic), tests/
apps/web/                              Next.js: src/app (rotas), src/components, src/lib
infra/postgres/init.sql                papel "mla" não-superusuário + bancos mla e mla_test
docker-compose.yml                     stack de desenvolvimento
docs/MLA_*.md                          documentação da versão web
```

Nada do desktop foi movido. Uma pasta `legacy/` exigiria mover `src/mla` e quebraria o build e o instalador. Ver
MLA_LEGACY_MIGRATION.md.

### API (`apps/api/src/mla_api/`)

| Módulo | Responsabilidade |
|---|---|
| `settings.py` | variáveis `MLA_*`, travas de produção |
| `db.py` | engine, sessão, **contexto de tenant** (`set_tenant` → `set_config('app.org_id', ..., true)`, reaplicado a cada transação) |
| `models.py` | users, organizations, memberships, auth_sessions, password_reset_tokens, audit_events, products; `TENANT_TABLES` |
| `security.py` | Argon2id, tokens opacos (SHA-256 no banco), matriz papel → permissões, limitador de login |
| `deps.py` | `current_auth` (cookie → sessão), `org_context` (associação obrigatória; 404 para não-membro), `require(perm)` |
| `routers/` | `auth` (cadastro, login, logout, me, redefinição de senha), `orgs` (organização, membros, auditoria), `products` (CRUD, busca, painel) |
| `domain/catalog.py` | GTIN (copiado do desktop), SKU, pendências internas do catálogo |
| `storage.py` | armazenamento por organização com proteção contra path traversal |
| `mailer.py` | e-mail em memória (testes) ou pasta outbox (dev). **SMTP de produção não implementado** |
| `audit.py` | registro de ações sensíveis, sem senha nem token |

## 4. Multiempresa: isolamento em camadas

1. **Rota:** todo recurso de organização fica sob `/api/orgs/{org_id}/...`. `org_context` exige associação. Quem não
   é membro recebe **404** (não descobre se a organização existe).
2. **Permissão:** `require("catalog.write")` etc. A matriz fica em `security.PERMISSIONS`.

   | Papel | Lê catálogo | Escreve catálogo | Vê membros | Gerencia membros | Auditoria | Organização |
   |---|---|---|---|---|---|---|
   | viewer | ✓ | | ✓ | | | |
   | editor | ✓ | ✓ | ✓ | | | |
   | admin | ✓ | ✓ | ✓ | ✓ (exceto proprietários) | ✓ | |
   | owner | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

   A organização nunca fica sem proprietário.
3. **Consulta:** toda leitura ou escrita de dado da organização filtra `organization_id` (ex.: `_get` em products: um
   id de outra organização devolve 404 mesmo pela rota da própria organização).
4. **Banco (PostgreSQL):** `products` e `audit_events` têm `ENABLE` + `FORCE ROW LEVEL SECURITY`, com a política
   `organization_id = current_setting('app.org_id')`. Sem tenant definido, nenhuma linha aparece. Uma escrita para
   outra organização é recusada pelo `WITH CHECK`. **A aplicação nunca conecta como superusuário**, porque
   superusuários ignoram RLS: `infra/postgres/init.sql` cria o papel `mla` sem `SUPERUSER`.
5. **Arquivos:** chave `orgs/<org_id>/<categoria>/<nome>`. A leitura confere o dono, os nomes passam por lista
   permitida e o caminho resolvido precisa continuar dentro da raiz. Nada fica em diretório público. O download
   passará por rota autorizada.
6. **Tarefas em segundo plano (etapa C):** todo job carrega `organization_id`, e o worker chama `set_tenant` antes de
   tocar dados. A mesma RLS vale para ele.

Teste de guarda: `test_every_org_owned_table_is_protected` falha se alguém criar uma tabela com `organization_id` sem
incluí-la em `TENANT_TABLES` (ou na lista explícita de exceções, hoje só `memberships`).

## 5. Autenticação e sessões

- Cadastro cria usuário + organização + vínculo de proprietário. Pode ser desligado com `MLA_ALLOW_SIGNUP=false`.
- Sessão no servidor: o cookie leva 32 bytes aleatórios e o banco guarda só o SHA-256. Validade de 7 dias, renovada
  quando passa da metade. Logout apaga a sessão.
- Login: mensagem idêntica para e-mail inexistente e senha errada; hash fictício verificado contra ataque de tempo;
  limitador de 5 falhas em 15 min por e-mail e por IP. **O limitador fica em memória do processo** e precisa ir para o
  banco ou Redis antes de rodar mais de uma instância.
- Redefinição de senha: resposta 202 sempre (sem enumerar contas); token de uso único, válido por 30 min, enviado no
  **fragmento** da URL (`#token=`), que não chega a servidor nem a log. A troca encerra todas as sessões.
- CSRF: `SameSite=Lax` + cabeçalho obrigatório `X-MLA-Client: web` em POST/PATCH/DELETE (formulários de outro site não
  conseguem enviá-lo).
- Cabeçalhos: `Cache-Control: no-store` na API, `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`. Documentação
  OpenAPI desligada em produção.

## 6. Modelo de dados (implementado até a migração 0002; o resto está planejado)

```
products ─┬─ product_variants (sku, atributos de variação, estoque, preço)          [0002 ✓]
          ├─ product_images (arquivo e/ou URL oficial do Gestor, ordem, variante)      [0002 ✓]
          ├─ product_channel_data (Código de catálogo ML, categoria por marketplace)  [0002 ✓]
          ├─ product_files · product_compatibilities (origem + verificação, como no desktop D-016)
          └─ product_changes (histórico por campo, como no desktop D-018)
import_batches → import_rows (plano persistido, como no desktop D-014) · jobs (fila)
seller_accounts [0002 ✓] · marketplace_templates (original imutável + sha256 + relatório do inspetor + prazo) [0002 ✓]
template_mappings (aba + linha de cabeçalho confirmada + coluna → campo | valor padrão) [0002 ✓]
listing_batches (status, validação, histórico) → listing_batch_items (produto) [0002 ✓]
exports (arquivo gerado, quem, quando) · batch_results (planilha de resultado importada, quando suportada)
```

Todas com `organization_id` + RLS. O dinheiro fica em centavos (inteiro), o peso em gramas e as dimensões em mm, como
no desktop.

## 7. Riscos e pendências

| Risco | Mitigação |
|---|---|
| Formato oficial da planilha desconhecido | Exportação bloqueada até analisar templates reais (MLA_MERCADOLIVRE_RESEARCH.md) |
| Imagens por URL pública (indício) exigiriam expor arquivos | Decidir na etapa D: URLs assinadas com validade × bucket público só de imagens aprovadas |
| RLS não testado de verdade neste computador | Teste marcado `postgres`; rodar com `MLA_TEST_DATABASE_URL` (compose ou CI) antes da etapa C |
| Limitador de login em memória | Mover para tabela antes de escalar horizontalmente |
| E-mail de produção ausente | SMTP/serviço transacional na etapa F; até lá, redefinição só em dev |
| Next.js 15 e Node pesam no notebook de 8 GB | Export estático; em produção não há Node |

## 8. Motor de templates do Mercado Livre

Regras citadas como P1/P2/P3 + página: ver MLA_MERCADOLIVRE_RESEARCH.md.

| Componente | Onde | Situação |
|---|---|---|
| **Template Registry** | `routers/listings.py` (`/templates`), tabela `marketplace_templates` | Implementado. O template pertence à organização **e** à conta de vendedor (P1 p.8). O original fica guardado byte a byte (`orgs/<org>/templates/<id>.xlsx`) com SHA-256; o mesmo arquivo não é registrado duas vezes na mesma organização e outras organizações nunca o veem. Registra a origem (categorias, códigos, links, Shopee, P1 p.5), o prazo e o status (inspected/invalid/archived) |
| **Template Inspector** | `domain/template_inspector.py` | Implementado, somente leitura. Antes do openpyxl, verifica o pacote (tamanho, ZIP, limite descompactado, macros e vínculos sinalizados e nunca carregados). Reporta abas e visibilidade, aba Ajuda, validações de dados, fórmulas, células mescladas, proteção, nomes definidos, marcadores da documentação **com coordenadas** e as 15 primeiras linhas. Não decide o layout: sugere linhas candidatas a cabeçalho e o usuário confirma |
| **Prazo** | inspetor + `PATCH /templates/{id}` | Implementado. Procura "até D de mês [de AAAA]" na aba Ajuda (P2 p.1–2). Sem ano no texto, o ano é deduzido e fica **não confirmado** até o usuário confirmar. Prazo vencido bloqueia o lote |
| **Attribute Mapper** | `domain/listing_rules.py` + `/templates/{id}/mapping` | Implementado. Usa a linha de cabeçalho confirmada, as colunas lidas do arquivo, "Obrigatório" na célula do cabeçalho ou logo abaixo dela, sugestões por sinônimo (só sugestão, salva apenas com confirmação), campo do catálogo, `attr:<nome>` ou valor padrão. O mapeamento é reutilizado por todos os lotes do template |
| **Validation Engine** | `domain/listing_rules.py` | Implementado. Cada problema traz severidade, **fonte** (`interna`, `documentacao`, `template`, `hipotese`), referência (PDF e página) e a correção. Hipóteses nunca geram erro |
| **Preview** | `GET /batches/{id}/preview` | Implementado: valores por linha (uma por variação, P1 p.6), fotos unidas por vírgula (P3 p.4). Nenhum arquivo é escrito |
| **Workbook Writer** | — | **Não implementado**, de propósito: `POST /batches/{id}/export` responde 409 até analisarmos um XLSX real (D-025). Requisito: escrever só nas células de dados de uma cópia, sem tocar abas, cabeçalhos, instruções, validações ou fórmulas (P1 p.6, P2 p.2) |
| **Error Importer** | — | **Não implementado**: depende de uma planilha de retorno real com "Resumo de erros" (P1 p.8) |

Estados do lote: `draft → needs_fix | ready` (pela validação; qualquer mudança de conteúdo volta para `draft`) →
`exported` (writer, pendente) → `sent_external` (somente com `confirm-sent` do usuário) → `result_received`
(somente com `confirm-result` do usuário; a planilha de erros importada fica para depois). Lotes enviados ficam
bloqueados para edição. Todo evento vai para `history` (quem, quando, o quê) e para a auditoria.

**Central de Fotos:** o catálogo guarda arquivos (JPG/PNG/WEBP verificados pelos bytes, até 10 MB, servidos só por
rota autorizada) e as **URLs oficiais** coladas do Gestor de fotos (o texto com várias URLs separadas por vírgula é
dividido). O limite de 10 fotos é do grupo do Gestor (P3 p.2): gera aviso na validação e não limita o catálogo. Não há
upload para o Gestor, porque não existe integração oficial documentada.

**Permissões:** contas de vendedor exigem `members.manage` (admin/owner); templates, mapeamentos e lotes exigem
`catalog.write` (editor+); leitura, `catalog.read`.
