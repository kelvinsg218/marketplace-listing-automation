# Progresso da missão MVP comercial (arquivo de retomada)

Ciclo: AUDITAR → PRIORIZAR → CORRIGIR → TESTAR → INTEGRAR → EMPACOTAR → DOCUMENTAR.
Auditoria: `docs/AUDITORIA_MVP.md`. Atualize este arquivo ao concluir cada item.

| # | Item | Situação |
|---|---|---|
| 1 | Auditoria + matriz + desktop×web + pesquisa ML/Shopee | Concluído |
| 2 | Correções da demo: sandbox do Edge, Reexecutar, valores em reais estritos, Dashboard, tela final da importação, aviso duplicado, rótulo ZIP, URLs sem query nos logs, seletor de conta | Concluído (testes unitários + navegador de conexão aprovados; telas conferidas em 1366×768 e 1100×700) |
| 3 | Multiempresa (pasta de dados isolada por empresa, troca de empresa) | Concluído (D-017; testes de registro, isolamento e troca na interface) |
| 4 | Histórico de alterações por campo + edição em lote segura | Concluído (D-018; migração 0008; aba Histórico no editor; diálogo com pré-visualização) |
| 5 | Exportação de anúncios preparados + relatório de pendências do catálogo | Concluído (D-019; XLSX/CSV, fotos copiadas, Anúncios → Exportar planilha; Catálogo → Importar e exportar → Relatório de pendências) |
| 6 | Cenário comercial (300 produtos, 500 imagens) com métricas reais | Concluído (`docs/DEMO_COMERCIAL.md`; integridade 100%; 3 problemas achados e corrigidos) |
| 7 | Suíte completa de testes | Concluído (230 aprovados, 0 falhos, incluindo 9 no Edge; novos testes de arquivos danificados, imagem corrompida, falha de rede, exportação, multiempresa, histórico e lote) |
| 8 | Build Windows + instalador/desinstalador testados | Pendente |
| 9 | Pacote de documentação comercial (PT-BR) | Pendente |
| 10 | Showcase + commits (push só com autorização) | Pendente |
