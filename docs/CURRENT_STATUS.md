# Estado atual — MLA Web 2.0

O aplicativo desktop foi descontinuado e removido (D-030; inventário em [MLA_LEGACY_MIGRATION.md](MLA_LEGACY_MIGRATION.md)).
Versão 2.0.0-alpha.0. API: 176 testes aprovados + 1 pulado (RLS). Web: typecheck e build ok. E2E no Edge: básico,
catálogo, imagens, anúncios em massa e fluxo oficial ok. Edge × Chrome: layout idêntico em 1366×768, 1440×900 e 1920×1080.

| Área | Situação |
|---|---|
| Template oficial real | Analisado (estrutura, fórmulas, validações, privacidade): [MLA_OFFICIAL_TEMPLATE_ANALYSIS.md](MLA_OFFICIAL_TEMPLATE_ANALYSIS.md) |
| Writer | Implementado e testado (sintético + cópia sanitizada do real). **Sem aceite real do ML ainda** |
| Regras adaptativas / Assistente de Correção | Implementados (determinísticos, sem IA externa); importar o arquivo de retorno = pendente |
| Isolamento | Aplicação: testado, inclusive regras e exportações. RLS (13 tabelas): escrito, **não executado** (papel `mla` não criado) |
| Central de Importações | XLSX/CSV/JSON/XML com simulação, processamento em segundo plano e relatório |
| Classificação | Categorias internas + classificação explicável + fila de revisão |
| Gestão de lotes | Continuar, renomear, duplicar, excluir rascunho, arquivar; assistente em 5 fases |
| Central de Imagens | Versões, aprovação, origem, importação por URL; **nenhum provedor de IA configurado** |
| Compatibilidades, fila/worker | Não iniciados |
| Firefox | Não testado (não instalado) |

Documentos: [MLA_WEB_ROADMAP.md](MLA_WEB_ROADMAP.md), [MLA_WEB_ARCHITECTURE.md](MLA_WEB_ARCHITECTURE.md),
[MLA_MERCADOLIVRE_RESEARCH.md](MLA_MERCADOLIVRE_RESEARCH.md), [MLA_OFFICIAL_TEMPLATE_ANALYSIS.md](MLA_OFFICIAL_TEMPLATE_ANALYSIS.md),
[MLA_WEB_UX_DESIGN.md](MLA_WEB_UX_DESIGN.md), [MLA_LEGACY_MIGRATION.md](MLA_LEGACY_MIGRATION.md).

Progresso por etapa: [MLA_IMPLEMENTATION_PROGRESS.md](MLA_IMPLEMENTATION_PROGRESS.md).
