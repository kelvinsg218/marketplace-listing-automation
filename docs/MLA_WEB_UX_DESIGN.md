# MLA Web: design system (preto e laranja)

Direção visual: dashboard escuro premium, preto profundo, laranja **só para ação e estado ativo**, tipografia firme,
cartões discretos. Brilho e gradiente quase não aparecem: um halo no login e o gradiente da barra de saúde do catálogo.
A referência é estética, não um layout a copiar.

## Tokens (`apps/web/src/app/globals.css`, bloco `@theme`)

Nenhuma cor, raio ou fonte fica fora dos tokens.

| Token | Valor | Uso |
|---|---|---|
| `bg` | `#090909` | fundo da página |
| `bg-2` | `#111111` | sidebar, campos, painéis laterais |
| `card` / `card-hover` | `#191919` / `#1f1f1f` | cartões, linha de tabela em hover |
| `line` / `line-strong` | `#292929` / `#3a3a3a` | bordas e bordas em hover |
| `fg` / `muted` / `faint` | `#F5F5F5` / `#A3A3A3` / `#737373` | texto principal, secundário, terciário |
| `accent` / `accent-2` | `#FF6500` / `#FF8A24` | botão primário, item ativo, foco / hover |
| `on-accent` | `#0B0B0B` | texto sobre laranja |
| `ok` / `warn` / `danger` / `info` | `#3CCB7F` / `#E8C547` / `#F0524A` / `#7AA7FF` | estados |
| raios | 6 / 10 / 14 px | badge / campo e botão / cartão |

Decisões de contraste:
- **O texto sobre o laranja é quase preto.** Branco sobre `#FF6500` dá ≈ 2,9:1 e reprova no WCAG AA. Preto dá ≈ 6,9:1.
- **O aviso é amarelo (`#E8C547`), não laranja,** para não ser confundido com a cor de ação.
- `muted` sobre `card` ≈ 7:1; `faint` serve só para texto auxiliar (≥ 4,5:1 sobre `bg`).

## Tipografia

- **Manrope** (interface): títulos em 700–800 com tracking negativo e corpo em 400–500. Números tabulares ligados
  globalmente (`tnum`), para que colunas de preço e estoque alinhem.
- **JetBrains Mono** em SKU e GTIN, que são códigos lidos caractere a caractere.
- Escala: título de página 26 px, título de seção 16 px, corpo 14 px, rótulos 13 px, metadados 12 px, cabeçalho de
  tabela 12 px em caixa alta com tracking.

## Componentes (`apps/web/src/components/ui.tsx`)

`Button` (primary/secondary/ghost/danger, `busy`), `Field` (rótulo + dica/erro ligados por `aria-describedby`),
`Input`/`Select`/`Textarea`, `Card`, `Badge` (neutral/accent/ok/warn/danger/info), `Skeleton`, `Alert`, `EmptyState`,
`Drawer` (painel lateral; tela cheia no celular; Esc fecha; o foco entra e volta), `PageHeader`. Placeholder honesto
para módulos futuros: `ComingSoon` (diz a etapa e o bloqueio).

## Padrões

- **Layout:** sidebar fixa de 272 px no desktop. Abaixo de `lg` vira barra superior com menu deslizante. Conteúdo com
  largura máxima de 1400 px e gutter de 16 px no celular. Testado sem rolagem horizontal em 390 px.
- **Navegação:** grupos Visão geral / Catálogo / Anúncios / Gestão. Item ativo com barra laranja à esquerda e ícone
  laranja. Módulos não construídos aparecem com o selo "em breve" e explicam o que falta, sem dado falso.
- **Métricas:** o painel mostra só números reais. Um módulo inexistente mostra "—" com a etapa que o entrega, nunca
  um zero inventado. Gráfico só quando há dado: hoje, a barra de saúde e a barra por status.
- **Tabelas:** cabeçalho discreto, hover de linha, colunas secundárias somem em telas menores (o SKU vai para baixo
  do nome) e há rolagem horizontal como último recurso.
- **Estados:** skeleton no primeiro carregamento, opacidade reduzida em recarga, empty state com próxima ação, erro em
  `Alert` com a mensagem do servidor (em português) e confirmação para exclusões.
- **Qualidade do produto:** badge Completo / N avisos / N erros, e no detalhe a lista de pendências com severidade
  (Erro bloqueia, Aviso pede atenção, Informação orienta). Essas pendências são regras **internas** do catálogo, não
  do Mercado Livre.
- **Acessibilidade:** foco visível laranja em todo elemento interativo, `aria-current` na navegação, rótulos ligados a
  campos, `role="meter"` na barra de saúde e `prefers-reduced-motion` respeitado.

## Telas

| Tela | Estado |
|---|---|
| Login, cadastro, recuperar senha, redefinir senha | Implementadas |
| Painel | Implementado (métricas reais do catálogo e atividade) |
| Catálogo (lista, busca, filtro, paginação, criar) e Produto detalhado (editar, pendências, excluir) | Implementados (campos da etapa B) |
| Organização (membros e papéis) | Implementada |
| Histórico (auditoria) | Implementado (proprietário e administrador) |
| Produto detalhado: Variações, Fotos (arquivo + URLs do Gestor, ordem), Mercado Livre (Código de catálogo ML) | Implementado |
| Central de Fotos (pendências de URL oficial + passo a passo do Gestor de fotos, P3) | Implementada |
| Marketplaces (contas de vendedor) | Implementada |
| Templates (registro, lista com prazo e situação) e detalhe (prévia da aba com marcadores, prazo, editor de mapeamento) | Implementados |
| Anúncios em massa: lista de lotes e wizard de 12 etapas | Implementado; Exportar, Importar resultados e Reprocessar mostram o bloqueio real |
| Lotes e exportações (situação e histórico) | Implementada |
| Importações, Compatibilidades, Configurações | Placeholder "em breve" com a etapa responsável |

Wizard de Anúncios em massa: trilho vertical de 12 etapas no desktop (horizontal com rolagem no celular), KPIs reais do lote (selecionados, linhas, completos, com erros, pronto), conta e template sempre visíveis. Cada problema mostra a severidade **e** a fonte (Regra interna / Documentação ML / Template / Hipótese), com a referência PDF+página. Plano original: Cada passo
mostra o progresso salvo no lote e permite voltar. A validação agrupa por severidade, com a correção inline na própria
linha do produto.

Capturas de referência: geradas pelo roteiro E2E (ver MLA_WEB_ROADMAP.md, "Como testar").
