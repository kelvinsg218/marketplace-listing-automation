# Estado atual — 19/10/2026, v0.2.0 (missão MVP comercial)

**MVP pronto para demonstração e para piloto supervisionado; não pronto para distribuição comercial.**
Progresso item a item: [PROGRESSO_MVP.md](PROGRESSO_MVP.md). Auditoria: [AUDITORIA_MVP.md](AUDITORIA_MVP.md).
Testes: 230 aprovados, 0 falhos (221 rápidos + 9 de ponta a ponta no Edge); pyflakes limpo. Banco: esquema v8.

| Área | Situação |
|---|---|
| Multiempresa | Feito e testado (D-017): pasta por empresa, troca no app, isolamento de catálogo, contas e sessões |
| Importação | Feito e testado: CSV/XLSX/JSON/XML/PDF/ZIP/pasta; sinônimos de ERP ampliados; arquivos danificados recusados com mensagem; foto corrompida vira pendência; pendências sem caminho local |
| Catálogo | Feito e testado: histórico por campo (D-018), edição em lote com prévia, valores em reais estritos no editor |
| Anúncios | Feito e testado: GTIN inválido bloqueia aprovação; Reexecutar usa o fluxo de anúncios com a mesma trava de aprovação |
| Exportação | Feito e testado (D-019): planilha intermediária XLSX/CSV com fotos; relatório de pendências do catálogo |
| Automação | Feito e testado no simulado: sandbox do Edge ligado; falhas de rede repetidas antes do clique de publicar (D-020) |
| Interface | Dashboard e tela "Concluído" da importação corrigidos para 1366×768 e 1100×700; seletor de conta; ações compactas no Catálogo |
| Distribuição | `tools/build_release.py` + `installer/`: build 0.2.0, autoteste do exe, instalar/atualizar/abrir/fechar/desinstalar testados nesta máquina (não em máquina limpa) |
| Cenário comercial | 300 produtos fictícios, 519 fotos, PDF e aplicações: integridade 100%, 6,6–11,9 s de processamento ([DEMO_COMERCIAL.md](DEMO_COMERCIAL.md)) |
| Mercado Livre / Shopee reais | **Não verificados.** Nenhuma conta real foi aberta; nenhuma publicação real |
| Inteligência de mercado / IA | Só estrutura (sem telas, sem coleta, sem IA ativa) |

## Limitações conhecidas
Lista para clientes: [comercial/LIMITACOES_CONHECIDAS.md](comercial/LIMITACOES_CONHECIDAS.md). Técnicas, além dela:
- Limites de título/fotos em `MARKETPLACE_RULES` ainda não confirmados nos formulários reais (D-009).
- `ImportExportService.import_csv/json` (legado) ainda existe; a interface usa a Central de Importações.
- Licença: avaliação por banco de dados (por empresa), nada é bloqueado (D-011).
