# Progresso de implementação — MLA Web 2.0

Atualizado em 02/11/2026. Status: ✅ concluída e testada · 🟡 parcial · ⏳ não iniciada · ⛔ bloqueada (com o motivo).

| Etapa | Status | Funcionalidades | Testes | Pendências | Próxima ação |
|---|---|---|---|---|---|
| 1. Refatoração (desktop → web) | ✅ publicada (`2c5ba19`, `0580c60`, `d92f8c8`) | Desktop removido; parsers, unidades, anos e leitura de imagens migrados para `apps/api` | 138 API + E2E básico e oficial | Nenhuma | — |
| 2. Central de Importações | ✅ publicada (`e689cdc`) | XLSX/CSV/JSON/XML; análise, abas, prévia, mapeamento sugerido (sinônimos), perfis salvos, simulação sem gravar, processamento em segundo plano em blocos de 200, progresso, cancelamento, histórico, relatório por linha, SKU repetido no arquivo, atualização só com confirmação (só campos preenchidos), variações por "produto pai", zeros à esquerda preservados, URLs de imagem da base guardadas como externas | `test_catalog_import.py` (6, inclui 1.000 linhas em 0,6 s) + E2E `catalog_flow.py` (100 produtos) | PDF e ZIP fora da tela; compatibilidades na importação; fila durável (hoje BackgroundTasks no mesmo processo) | Fila PostgreSQL + worker separado |
| 3. Classificação inteligente | ✅ publicada (commit "feat: add intelligent product categorization and review") | Árvore interna por organização (exemplo opcional), regras por expressão/palavra/exclusão, pontuação explicável, alta/necessita confirmação/não classificado, fila de revisão, confirmação individual e em lote, confirmados nunca alterados, alteração de regra auditada com o valor anterior, categoria oficial do ML separada e "não confirmada" até o usuário confirmar | `test_classification.py` (14, inclui 5.000 produtos em ~11 s) + E2E (84/100 com alta confiança, 16 corretamente sem categoria) | Reverter regra pela interface (hoje via auditoria); classificação em lote por regra de "semelhantes" | Ligar categoria interna → template/aba do ML no lote |
| 4. Central de Imagens / Estúdio de IA | ✅ publicada (`04ef11a`, provedor OpenAI `21b94d4`) | Busca por SKU/nome/GTIN, filtros, visualizador, upload, importação por URL (SSRF), URLs do Gestor, origem, versões com prompt, aprovar/rejeitar/principal; só aprovadas vão para planilhas. Provedor OpenAI (`gpt-image-2`, `/v1/images/edits`) real, **desligado**; orçamento interno US$ 5 com reserva por pedido e bloqueio | `test_images.py` (14), `test_openai_images.py` (10, transporte falso), `images_flow.py` | Chave + `MLA_IMAGE_AI_ENABLED=true` + autorização sua; **nenhuma chamada paga feita** | Configurar a chave (guia em MLA_SETUP_GUIDE.md) |
| 5. Anúncios em massa (melhorias) | ✅ publicada (`70c45ea`) | Continuar de onde parou, renomear, duplicar, excluir rascunho (só sem exportações), arquivar/desarquivar; assistente em 5 fases (mesmas validações); filtro por categoria nos produtos | `test_batch_management.py` (4), `official_flow.py`, `bulk_flow.py` | Nenhuma | — |
| 6. Contas reais do ML (OAuth) | ✅ publicada (sem app real do ML) | OAuth oficial (código + PKCE, `state` de uso único ligado ao usuário), identificação por `/users/me`, conexão por conta de vendedor, tokens AES-256-GCM, renovação com trava (refresh de uso único), detecção de revogação (`invalid_grant`), estados, desconexão, auditoria, tela em Marketplaces | `test_ml_oauth.py` (9, Mercado Livre falso) | **App no portal de desenvolvedores do ML** (client id/secret, redirect URI https) e chave de cifragem; validar com uma conta real | Criar o app no ML (guia em MLA_SETUP_GUIDE.md) |
| 7. Importador de erros | ⛔ falta um arquivo de retorno real | Assistente aceita o "Resumo de erros" colado | — | Ler o arquivo devolvido pelo ML | Aguardar um exemplo real |
| 8. Segurança | 🟡 | Isolamento na aplicação testado em todos os módulos (19 tabelas com `organization_id`); uploads verificados; teste RLS agora cobre todas as tabelas e só roda em banco `*_test`; `init.sql` idempotente | `test_isolation.py` | **RLS em PostgreSQL real não executado**: falta a senha do `postgres` | Rodar `init.sql` (você) |
| 9. Interface | ✅ | Edge = Chrome nas 3 resoluções; menu cabe em 1366×768 com 16 itens | `browser_compare.py`, `catalog_flow.py` | Firefox não testado | — |
| 10. Fluxo de demonstração | 🟡 | Passos 1–5 cobertos por `catalog_flow.py` (100 produtos); passos 6–13 por `official_flow.py` | E2E | Unir num único roteiro; etapas 4 e 5 prontas | Unir o roteiro |

## Arquivos das etapas 2 e 3 (publicados)

- **API:** `routers/imports.py`, `services/catalog_import.py`, `routers/categories.py`, `domain/classifier.py`,
  migrações `0004_imports.py` e `0005_categories.py`, `models.py` (ImportJob, ImportProfile, Category,
  ProductClassification), `main.py`.
- **Testes:** `tests/test_catalog_import.py`, `tests/test_classification.py`.
- **Web:** `app/(app)/importacoes/page.tsx` (substitui o "em breve"), `app/(app)/categorias/page.tsx`, botão
  "Importar produtos" no catálogo, menu.
- **E2E:** `apps/web/e2e/catalog_flow.py`.

## Arquivos da etapa 4 (Central de Imagens)

- **API:** `models.py` (`ProductImage`: origem, URL externa, status, versão de origem, prompt, provedor, revisão),
  migração `0007_image_versions.py`, `routers/images.py`, `services/image_ai.py` (interface de provedor),
  `services/safe_fetch.py` (busca por URL: só https, sem redirecionamento, sem endereços internos, 10 MB),
  `routers/media.py`, `services/listing_data.py` (só aprovadas), `settings.py` (`image_ai_provider`), `main.py`.
  Testes: `tests/test_images.py` (o provedor de IA dos testes é um dublê local).
- **Web:** `fotos/page.tsx` (Central de Imagens + Estúdio de IA), `shell.tsx` (nome no menu).
- **E2E:** `images_flow.py` (novo); `bulk_flow.py`, `catalog_flow.py` atualizados.
- **Validação (02/11/2026):** API 176 aprovados + 1 pulado (RLS); pyflakes ok; `next build` ok; E2E imagens, básico,
  catálogo, anúncios em massa e oficial ok.

## Integração OpenAI e etapa 6 (publicadas)

- **OpenAI:** `services/openai_images.py` (provedor real, transporte injetável), `services/image_ai.py` (dois
  interruptores, regra de preservação do produto), `services/ai_budget.py` (reserva/liquidação), modelo `AiSpend` e
  colunas de custo em `ProductImage`, migração `0008_ai_spend.py`, `routers/images.py`, `settings.py`, `.env.example`,
  `fotos/page.tsx` (modelo, orçamento, prévia). Testes: `test_openai_images.py`; `conftest.py` nunca lê `.env`.
- **Etapa 6:** `services/ml_oauth.py`, `services/token_crypto.py`, `routers/ml_connections.py`, modelos
  `MarketplaceConnection` e `OAuthState` (tabelas com RLS), migração `0009_marketplace_connections.py`,
  `marketplaces/page.tsx`, dependência `cryptography==46.0.7`. Testes: `test_ml_oauth.py`.
- **PostgreSQL:** `infra/postgres/init.sql` idempotente; `test_isolation.py` reforçado.
- **Validação (02/11/2026):** API 195 aprovados + 1 pulado (RLS); pyflakes ok; typecheck ok; E2E imagens, smoke e
  oficial ok; tela de Marketplaces conferida no Edge.
