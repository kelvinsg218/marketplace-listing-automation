# Pesquisa — Anunciador em Massa do Mercado Livre

Atualizado em 01/11/2026 com os três PDFs oficiais da Central de aprendizagem que o usuário salvou do próprio
navegador, todos em 01/11/2026. Li o texto e as capturas de tela de cada página. Os PDFs ficam fora do repositório.

| Ref. | Arquivo | Página oficial | Páginas |
|---|---|---|---|
| **P1** | `Central de aprendizagem.pdf` | "Conheça como usar o Anunciador em massa em 5 passos" (`/aprender/nota/anuncie-varios-produtos-de-uma-vez-nuevo`) | 10 |
| **P2** | `Central de aprendizagem_2.pdf` | "Aprenda a preencher a planilha Excel para anunciar em massa" (`/aprender/nota/entenda-como-preencher-sua-planilha-excel-para-anunciar-em-m`) | 5 |
| **P3** | `Central de aprendizagem_3.pdf` | "Como usar o Gestor de fotos para anunciar em massa" (`/aprender/nota/evite-erros-nas-fotos-da-planilha-usando-o-gestor-de-fotos`) | 4 |

Citação: `P2 p.3` = PDF P2, página 3; "(captura)" = a informação vem de uma imagem ilustrativa, não do texto.

**Classificação** (as categorias não se misturam):
- **DOC:** confirmado pela documentação oficial.
- **TPL:** confirmado por template real. *Hoje nada: nenhum XLSX oficial foi analisado.*
- **TESTE:** confirmado por teste do MLA contra o Mercado Livre real. *Hoje nada.*
- **HIP:** hipótese, inferida das capturas ou de terceiros. Não vira regra bloqueante.
- **PEND:** desconhecido; depende de template ou de planilha de retorno reais.

## 1. Fluxo do Anunciador em massa

| # | Regra | Classe | Fonte |
|---|---|---|---|
| F1 | Anuncia vários produtos de uma vez por planilha Excel, inclusive em categorias diferentes ao mesmo tempo | DOC | P1 p.1 |
| F2 | Acesso: lista de anúncios → "Anunciar" → "Em massa"; ou Vender → Produtos → "Ir para o Anunciador em Massa" | DOC | P1 p.1 |
| F3 | A planilha pode ser gerada de três formas: (a) códigos universais **ou** seleção de categorias; (b) links de produtos já anunciados no ML ou em outros marketplaces; (c) planilhas da Shopee ("Envie seus modelos da Shopee") | DOC | P1 p.5 (texto + captura) |
| F4 | Pelas formas (a) por código, (b) e (c), vários campos já vêm preenchidos: "basta revisar" | DOC | P1 p.6; P2 p.1 |
| F5 | Envio: voltar à ferramenta → "Envie a planilha Excel que você baixou"; o ML valida as informações | DOC | P1 p.6–7 (captura p.7) |
| F6 | Depois que o carregamento começa, **não pode ser interrompido**; leva alguns minutos; dá para sair da tela | DOC | P1 p.7–8 |
| F7 | O ML envia e-mail quando a criação termina e e-mail confirmando os anúncios criados | DOC | P1 p.8 |
| F8 | **Só aceita planilhas baixadas a partir da própria conta** | DOC | P1 p.8 |
| F9 | **Limite de 10.000 anúncios criados por dia** | DOC | P1 p.8 |
| F10 | Com erros, é possível baixar um **novo arquivo só com os anúncios não criados**, com a coluna "Resumo de erros"; corrigir e reenviar pelo passo 4 | DOC | P1 p.8 |
| F11 | Há uma tela de resultado ("Alguns anún…", "Saiba mais informa…") com itens de sucesso e de erro | DOC (captura parcial) | P1 p.9 |

## 2. Estrutura da planilha

| # | Regra | Classe | Fonte |
|---|---|---|---|
| E1 | Existe uma aba **"Ajuda"** com dicas, a **data limite para enviar a planilha** (depois disso é preciso baixar outra), a organização do arquivo, o significado de cada tipo de célula, como adicionar fotos e como criar variações | DOC | P2 p.1; P1 p.5 |
| E2 | Na captura, "Ajuda" é a primeira aba, seguida de "Categoria 1, 2, 3"; tem as seções "1. Como é a estrutura da planilha Excel?" (legenda de cores amarelo/laranja/verde/azul), "2. Como anuncio vários produtos de uma vez?", "3. Como adiciono as fotos…", "4. Como crio variações?" e um bloco "Enviar planilha — Faça isso até 10 de setembro" | DOC (captura) | P2 p.2 |
| E3 | **Uma aba por categoria baixada**, com o nome da categoria; os campos variam por categoria | DOC | P2 p.2; P1 p.6 |
| E4 | **Cada linha preenchida numa aba vira um anúncio** | DOC | P1 p.6 |
| E5 | **Não renomear abas, não adicionar abas, não mover colunas, não alterar nomes, não editar o que já está no arquivo, não apagar as linhas coloridas de títulos e instruções** | DOC | P1 p.6; P2 p.2 |
| E6 | Na captura de uma aba: 1ª linha com o caminho da categoria ("Alimentos e bebidas > Biscoitos"), linha com o nome ("Biscoitos"), linha de cabeçalhos coloridos, linha com marcação "Obrigatório", linhas cinza de instrução e só então as linhas brancas de dados | DOC (captura) | P2 p.4; P3 p.4 |
| E7 | Os campos necessários vêm marcados **"Obrigatório"**; o ML recomenda preencher todos | DOC | P2 p.4 (texto + captura) |
| E8 | Há **links de ajuda** ao longo do arquivo; alguns servem para obter dados (ex.: URLs das fotos) | DOC | P2 p.4 |
| E9 | **"Resumo de erros"** é a última coluna do arquivo; indica dados obrigatórios não preenchidos; fica **cinza** quando a linha está completa. Exemplo de conteúdo: "- Marca / - Estoque / - Forma de envio" | DOC (texto + captura) | P2 p.4–5 |
| E10 | Na captura, a primeira coluna de dados tem uma lista suspensa com o valor "Lista geral" | DOC (captura); **significado PEND** | P3 p.4 |
| E11 | Os números exatos de linha/coluna, as abas ocultas, as validações de dados, as fórmulas (inclusive se "Resumo de erros" é calculado por fórmula), a proteção e os metadados de conta | PEND | — |

## 3. Catálogo do Mercado Livre

| # | Regra | Classe | Fonte |
|---|---|---|---|
| C1 | Alguns dados podem vir preenchidos com informações do catálogo do ML | DOC | P2 p.2 |
| C2 | Coluna **"Código de catálogo ML"** (na captura, "Código do catálogo ML", primeira coluna amarela): dá para colar o código achado no buscador de produtos do ML | DOC | P2 p.2, p.4 (captura) |
| C3 | Com código de catálogo, não é preciso preencher tudo: as colunas dispensáveis mostram **"Para catálogo, não é necessário preencher este dado."** e têm células **cinza-claro** | DOC | P2 p.3 |
| C4 | Produto fora do catálogo: preencher manualmente; os obrigatórios vêm marcados "Obrigatório" | DOC | P2 p.4 |
| C5 | Quais colunas exatamente são dispensadas com catálogo, por categoria | PEND (vem do template) | — |

## 4. Variações

| # | Regra | Classe | Fonte |
|---|---|---|---|
| V1 | Variações (tamanhos, cores etc.) são criadas **duplicando linhas** da planilha | DOC | P1 p.6 |
| V2 | A aba Ajuda explica como criar variações | DOC | P2 p.1–2 |
| V3 | Como as linhas se agrupam no mesmo anúncio (título idêntico? coluna própria?), que colunas de variação existem e o SKU por variação | PEND (indício de 2019: título idêntico, SKU/EAN/fotos por variação, HIP) | — |

## 5. Fotos e Gestor de fotos

| # | Regra | Classe | Fonte |
|---|---|---|---|
| G1 | As fotos entram na coluna **"Fotos"**, que tem o link "Obter URLs no Gestor de fotos" | DOC | P1 p.6; P3 p.1–2 (captura) |
| G2 | Na captura, a coluna "Fotos" está marcada "Obrigatório" (categoria Biscoitos) | DOC (captura) — vale para outras categorias: PEND | P3 p.4 |
| G3 | Gestor: "Criar grupo de fotos" com um nome (recomendado: o nome do produto); **até 10 fotos por grupo**; ordem por arrastar | DOC | P3 p.2 |
| G4 | O gestor verifica requisitos básicos e informa o que corrigir; ainda assim, conferir os critérios de qualidade da categoria | DOC | P3 p.1 |
| G5 | "Copiar URLs" e colar na célula do produto correspondente | DOC | P3 p.3 |
| G6 | Exemplo da célula: duas URLs `https://http2.mlstatic.com/D_NQ_NP_...-F.jpg` **separadas por vírgula, sem espaço** | DOC (captura) | P3 p.4 |
| G7 | O gestor não baixa imagens de anúncios existentes | DOC | P3 p.4 |
| G8 | Com geração por códigos, links ou Shopee, a coluna Fotos já vem preenchida | DOC | P1 p.6 |
| G9 | Usar só imagens próprias ou autorizadas (propriedade intelectual) | DOC | P1 p.6 |
| G10 | Se o ML aceita URLs que não sejam do Gestor (outros domínios) | PEND (indício de 2019: "URLs públicas", HIP) | — |
| G11 | API pública de upload para o Gestor de fotos | Não documentada nos PDFs; não implementar | — |

## 6. API pública (complemento, consultada em 01/11/2026)

| Endpoint | Status | Uso no MLA |
|---|---|---|
| `GET /categories/{id}/attributes` | 200 | Atributos com `tags.required`, `value_type`, `hint`. Cruzar com as colunas do template (TESTE da API, não da planilha) |
| `GET /sites/MLB/domain_discovery/search?q=` | 200 | Sugestão de categoria |
| `GET /sites/MLB/listing_types` | 403 sem login | — |

## 7. Consequências para o MLA (requisitos derivados)

1. **Template = arquivo oficial da organização e da conta de vendedor** (F8). Fica guardado intacto com SHA-256 e
   nunca é compartilhado entre organizações. Sem template legítimo, não há exportação.
2. **Escrita só em linhas de dados, numa cópia** (E5): nunca renomear, criar, mover ou apagar abas, colunas ou linhas
   de instrução. O writer só começa depois de um XLSX real (E11).
3. **Prazo** (E1): o inspetor procura o texto de prazo na aba Ajuda. Encontrado, guarda o texto literal e a data
   interpretada. O ano não aparece no exemplo ("até 10 de setembro"), então a data fica **marcada como inferida até o
   usuário confirmar**. Vencida, o MLA bloqueia a exportação e pede um novo download.
4. **Dois perfis de produto** (C2–C4): com código de catálogo ML, as colunas dispensadas vêm do template; sem ele, os
   "Obrigatório" valem.
5. **Variações = linhas duplicadas** (V1). A regra de agrupamento é PEND: o mapeamento de variações espera o template.
6. **Fotos** (G1–G6): a Central de Fotos registra, por produto ou variação, os **URLs oficiais** obtidos no Gestor.
   Exportação = URLs na ordem, separados por vírgula (G6). Mais de 10 URLs gera aviso: o limite é do grupo do Gestor
   (G3), não do catálogo. URL fora de `mlstatic.com` gera aviso (G10 é PEND), não erro.
7. **Validação própria ≠ validação oficial** (E9, F5): o MLA indica a fonte de cada regra (interna, documentação,
   template) e nunca diz "aceito pelo ML". A coluna "Resumo de erros" do arquivo e a planilha de retorno (F10) são
   evidências oficiais.
8. **Lotes de até 10.000 linhas por dia por conta** (F9): o MLA alerta acima disso e sugere dividir.
9. **Envio é manual** (F5–F7): o MLA mostra o passo a passo e registra "Enviado externamente" só com confirmação do
   usuário, e "Resultado recebido" só com o e-mail confirmado pelo usuário ou a planilha de erros importada (F10).
10. **Três origens de planilha** (F3): o MLA registra a origem informada pelo usuário (categorias, códigos
    universais, links, Shopee). Uma planilha gerada por link ou Shopee chega pré-preenchida (F4) e o writer não pode
    sobrescrever dados existentes sem confirmação. Importar uma planilha da Shopee no MLA é **outra coisa** que a
    conversão feita pelo ML: adaptador separado, na etapa C.

## 8. O que ainda falta (para a geração definitiva)

1. **Templates XLSX intactos** baixados da sua conta, no Anunciador em massa: (a) autopeças por categoria; (b) uma
   categoria com variações (roupa ou calçado); (c) se possível, um gerado por código universal ou link, para ver o
   pré-preenchimento. Coloque-os em `docs/ml-research/` (ignorada pelo git).
2. **Uma planilha de retorno com "Resumo de erros"** (F10), de preferência de um envio de teste com dados fictícios em
   rascunho, se houver essa opção. Sem ela o Error Importer não pode ser finalizado.
3. Com (1): rodar o Template Inspector do MLA nos arquivos e preencher a seção 9.

## 9. Estrutura confirmada por template real

*Vazia.* Nenhum XLSX oficial foi analisado ainda.
