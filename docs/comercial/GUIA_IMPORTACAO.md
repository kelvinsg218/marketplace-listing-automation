# Guia de importação de catálogos

## Formatos aceitos
| Formato | Observações |
|---|---|
| CSV | UTF-8 ou Windows-1252 (ANSI); separador `;`, `,`, tabulação ou `|` detectado sozinho |
| Excel (XLSX) | Usa a primeira aba com dados (abas de capa são puladas) ou a aba escolhida; macros nunca são executadas |
| JSON / XML | Listas de produtos, inclusive com variações aninhadas; XML com entidades (DOCTYPE) é recusado por segurança |
| PDF | Só PDF com texto. Tabela alinhada entra direto; linhas ambíguas ficam para você decidir |
| ZIP | Planilha + fotos; executáveis, scripts e planilhas com macro são ignorados e nunca executados |
| Pasta de fotos | Liga as fotos pelo SKU no nome do arquivo |

## Prepare a planilha do fornecedor
1. **Uma linha por produto ou por variação.** Variações levam o SKU do produto pai numa coluna própria
   ("SKU Pai") e o nome da variação ("Variação": Preto, 220 V…).
2. **Uma coluna de código (SKU) sem repetição.** SKU repetido no arquivo é recusado (a primeira ocorrência entra).
3. **GTIN/EAN como texto.** No Excel, formate a coluna como Texto antes de colar: códigos em notação científica
   (`7,89E+12`) perderam dígitos e são recusados.
4. **Preços em reais**: `129,90`, `R$ 1.234,56` ou `129.90`. Textos como `12,3x` ou `9,99 reais` são recusados.
5. **Estoque inteiro e não negativo.**
6. **Medidas** em colunas separadas (Comp/Larg/Alt em cm, Peso em kg ou g) ou "Dimensões" (C×L×A).

## Nomes de coluna reconhecidos (exemplos)
| Campo do MLA | Nomes reconhecidos |
|---|---|
| SKU | SKU, Código do SKU; Código, Cód. Produto, Referência, Código interno (confirmar) |
| Nome do produto | Nome, Produto, Descrição do item (confirmar) |
| Título do anúncio | Título, Título do anúncio, Título para anúncio |
| Descrição | Descrição completa, Descrição longa, Detalhes |
| GTIN/EAN | EAN, GTIN, EAN13, Código de barras |
| Preço / custo | Preço, Preço venda, Valor venda / Custo, Preço de custo |
| Estoque | Estoque, Qtd estoque, Saldo (confirmar), Quantidade (confirmar) |
| Medidas | Comprimento/Comp (cm), Largura/Larg (cm), Altura/Alt (cm), Peso (kg) |
| Compatibilidade | SKU, Marca do veículo, Modelo do veículo, Ano inicial, Ano final, Anos |

Colunas não reconhecidas podem ser mapeadas à mão; **Salvar como modelo** reaproveita o mapeamento no próximo
arquivo do mesmo fornecedor.

## Fotos
- Nomeie pelo SKU: `ABC-1.jpg` (principal), `ABC-1_2.jpg`, `ABC-1-3.jpg`, `ABC-1 (4).jpg`.
- Formatos JPG, PNG ou WEBP; recomendado ao menos 500 px no menor lado.
- Fotos citadas na planilha e não encontradas, ou arquivos corrompidos, ficam como **mídia pendente** no produto.
  Quando a foto chegar, importe a pasta de novo: a pendência é resolvida pelo nome do arquivo.

## O que acontece com os erros
| Situação | Resultado |
|---|---|
| Preço inválido, estoque negativo, GTIN em notação científica, SKU repetido ou ausente | Linha recusada com o motivo; o resto do arquivo entra |
| GTIN com dígito verificador errado | Produto entra com aviso e o código como veio; o anúncio fica bloqueado até corrigir |
| Produto sem título, descrição ou foto | Entra como Incompleto; aparece no relatório de pendências |
| Linha ambígua do PDF | Fica para você incluir ou ignorar |
| Produto já cadastrado | Mostra cada alteração "atual → arquivo"; você decide atualizar ou ignorar |

Depois de importar, use **Catálogo → Importar e exportar → Relatório de pendências do catálogo** para devolver ao
fornecedor a lista do que falta.
