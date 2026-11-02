# Progresso de implementação — MLA Web 2.0

Atualizado em 02/11/2026. Status: ✅ concluída e testada · 🟡 parcial · ⏳ não iniciada · ⛔ bloqueada (com o motivo).

| Etapa | Status | Funcionalidades | Testes | Pendências | Próxima ação |
|---|---|---|---|---|---|
| 1. Refatoração (desktop → web) | ✅ publicada (`2c5ba19`, `0580c60`, `d92f8c8`) | Desktop removido; parsers, unidades, anos e leitura de imagens migrados para `apps/api` | 138 API + E2E básico e oficial | Nenhuma | — |
| 2. Central de Importações | ✅ publicada (`e689cdc`) | XLSX/CSV/JSON/XML; análise, abas, prévia, mapeamento sugerido (sinônimos), perfis salvos, simulação sem gravar, processamento em segundo plano em blocos de 200, progresso, cancelamento, histórico, relatório por linha, SKU repetido no arquivo, atualização só com confirmação (só campos preenchidos), variações por "produto pai", zeros à esquerda preservados, URLs de imagem da base guardadas como externas | `test_catalog_import.py` (6, inclui 1.000 linhas em 0,6 s) + E2E `catalog_flow.py` (100 produtos) | PDF e ZIP fora da tela; compatibilidades na importação; fila durável (hoje BackgroundTasks no mesmo processo) | Fila PostgreSQL + worker separado |
| 3. Classificação inteligente | ✅ publicada (commit "feat: add intelligent product categorization and review") | Árvore interna por organização (exemplo opcional), regras por expressão/palavra/exclusão, pontuação explicável, alta/necessita confirmação/não classificado, fila de revisão, confirmação individual e em lote, confirmados nunca alterados, alteração de regra auditada com o valor anterior, categoria oficial do ML separada e "não confirmada" até o usuário confirmar | `test_classification.py` (14, inclui 5.000 produtos em ~11 s) + E2E (84/100 com alta confiança, 16 corretamente sem categoria) | Reverter regra pela interface (hoje via auditoria); classificação em lote por regra de "semelhantes" | Ligar categoria interna → template/aba do ML no lote |
| 4. Central de Imagens / Estúdio de IA | ⏳ | (Central de Fotos atual: arquivo + URL do Gestor) | — | Visualizador, versões, aprovação, provedores de IA com consentimento | Modelo de versões de imagem |
| 5. Anúncios em massa (melhorias) | 🟡 | Writer, regras e assistente prontos | — | Ações por lote (renomear, duplicar, excluir rascunho, arquivar); fluxo em 5 fases | Menu de ações por lote |
| 6. Contas reais do ML (OAuth) | ⏳ | Cadastro nominal de contas | — | OAuth web com tokens cifrados | Portar o cliente OAuth do desktop (histórico do git) |
| 7. Importador de erros | ⛔ falta um arquivo de retorno real | Assistente aceita o "Resumo de erros" colado | — | Ler o arquivo devolvido pelo ML | Aguardar um exemplo real |
| 8. Segurança | 🟡 | Isolamento na aplicação testado em todos os módulos; uploads verificados por conteúdo e tamanho | — | **RLS em PostgreSQL real** (papel `mla` não criado) | Rodar `infra/postgres/init.sql` |
| 9. Interface | ✅ | Edge = Chrome nas 3 resoluções; menu cabe em 1366×768 com 16 itens | `browser_compare.py`, `catalog_flow.py` | Firefox não testado | — |
| 10. Fluxo de demonstração | 🟡 | Passos 1–5 cobertos por `catalog_flow.py` (100 produtos); passos 6–13 por `official_flow.py` | E2E | Unir num único roteiro; passos 14–15 dependem da etapa 5 | Após a etapa 5 |

## Arquivos das etapas 2 e 3 (publicados)

- **API:** `routers/imports.py`, `services/catalog_import.py`, `routers/categories.py`, `domain/classifier.py`,
  migrações `0004_imports.py` e `0005_categories.py`, `models.py` (ImportJob, ImportProfile, Category,
  ProductClassification), `main.py`.
- **Testes:** `tests/test_catalog_import.py`, `tests/test_classification.py`.
- **Web:** `app/(app)/importacoes/page.tsx` (substitui o "em breve"), `app/(app)/categorias/page.tsx`, botão
  "Importar produtos" no catálogo, menu.
- **E2E:** `apps/web/e2e/catalog_flow.py`.
