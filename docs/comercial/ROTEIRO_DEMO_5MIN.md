# Roteiro de demonstração (5 minutos)

**Preparação (antes da reunião):** rode `demo\pilot_scenario.py` uma vez para ter os arquivos fictícios em
`demo\pilot\fixtures`. Abra o MLA numa empresa de demonstração vazia (botão da empresa → **Nova empresa…** →
"Demonstração"). Nunca use dados reais de outro cliente numa demonstração.

| Tempo | O que mostrar | O que dizer |
|---|---|---|
| 0:00–0:30 | Pasta `fixtures` com a planilha, o PDF e 519 fotos | "Este é o tipo de material que chega do fornecedor: colunas com nomes próprios, fotos soltas, erros." |
| 0:30–1:45 | Importações → Nova importação → `catalogo-aurora.xlsx`: prévia, mapeamento (19 de 20 colunas sugeridas, 2 para confirmar), revisão com as linhas recusadas | "Nada é gravado antes de você ver. Cada linha recusada tem o motivo: preço com letra, GTIN estragado pelo Excel, SKU repetido." |
| 1:45–2:15 | Confirmar → tela Concluído com as contagens e as linhas a corrigir | "A gravação é tudo ou nada. O que não entrou vira uma lista para devolver ao fornecedor." |
| 2:15–2:45 | Associar imagens de uma pasta → `fotos` | "As fotos são ligadas pelo código do produto. As que faltam ou vieram corrompidas ficam marcadas." |
| 2:45–3:30 | Catálogo: filtro Incompleto; abrir um produto; aba Histórico; selecionar vários → Editar em lote → Pré-visualizar | "Cada alteração fica registrada com a origem. Correções em lote só em campos descritivos, sempre com prévia." |
| 3:30–4:15 | Preparar anúncios → Anúncios: um anúncio bloqueado por GTIN inválido; aprovar um pronto | "O MLA não inventa dado nem deixa passar código errado. A aprovação é sempre de uma pessoa." |
| 4:15–5:00 | Exportar planilha → abrir o Excel (abas Anúncios, Pendências, Resumo) e a pasta de fotos | "Esta planilha está conferida e pronta para ir ao modelo oficial do marketplace, com o seu acompanhamento." |

## Perguntas frequentes
- **Publica direto no Mercado Livre?** Ainda não. Hoje entregamos a planilha conferida; a publicação direta depende
  de autorização da conta e validação supervisionada.
- **Meus dados vão para a nuvem?** Não. Ficam no computador, numa pasta por empresa, com backup.
- **Quanto tempo economiza?** Ainda não medimos contra o processo manual; o piloto mede isso com a sua base.
- **Funciona com o meu ERP?** Aceita CSV, Excel, JSON, XML, PDF e ZIP. Colunas não reconhecidas são mapeadas uma vez
  e salvas como modelo.
