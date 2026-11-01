# Análise do template oficial do Anunciador em Massa

Arquivo analisado em 01/11/2026: um XLSX baixado da conta do usuário. O original fica em `docs/ml-research/`, que o
git ignora, e **não é versionado**. Este documento descreve estrutura e regras. Valores que identificam conta, vendedor
ou loja não aparecem aqui, nem em testes ou logs.

Ferramentas usadas: `domain/template_inspector.py` (somente leitura, openpyxl sem macros), leitura direta do XML
interno e `apps/api/tools/sanitize_template.py`.

## 1. Privacidade (auditoria antes do uso)

| Onde | O que existe | Tratamento |
|---|---|---|
| `docProps/core.xml` | Vazio (sem autor, empresa ou datas) | — |
| `docProps/custom.xml`, macros, vínculos externos de dados | Não existem | — |
| Aba **"extra info"** (`veryHidden`), linha 1 | **Vínculo do arquivo:** A1 é um identificador com número de 10 dígitos + "bulk-sell" + código hexadecimal; B1 é uma data; C1 é um UUID | Sensível: provavelmente liga o arquivo à conta e à sessão do Anunciador. Não é exibido no MLA (abas ocultas não têm prévia) e é trocado na cópia sanitizada |
| "extra info", listas de "Loja Oficial" | Nomes das lojas oficiais da conta | Dado comercial: trocado por "Loja Exemplo N" na cópia sanitizada |
| `sharedStrings.xml` | É onde os 4 valores acima ficam guardados (1 ocorrência cada) | A sanitização mexe só nesta parte |
| Hiperlinks (`_rels`) | Só páginas genéricas de ajuda/ferramentas do ML (gestão de fotos, upload, catálogo, simulador de custos) | Nenhum identificador de conta nos links |
| Dados de produtos | Nenhum preenchido (só valores padrão do modelo) | — |

**Cópia sanitizada** em `docs/ml-research/sanitized/template-sanitizado.xlsx` (também ignorada pelo git):
- só `xl/sharedStrings.xml` difere do original; as outras 34 partes são idênticas byte a byte;
- o script recusa gravar a cópia se algum valor original sobrar;
- a estrutura relida pelo inspetor é a mesma;
- a cópia **não serve para envio ao ML**, porque o vínculo foi removido.

## 2. Abas

| # | Aba | Estado | Conteúdo |
|---|---|---|---|
| 1 | Ajuda | visível | Instruções, legenda de cores, links, **data limite** (C26: "Faça isso antes de 1 de dezembro"), regras de fotos e variações. 8 imagens (drawing1) |
| 2 | extra info | **veryHidden** | Linha 1 = vínculo (ver §1); linhas 2–100 = listas das validações de dados, em blocos por categoria |
| 3–8 | Protetor de Sapatos, Conjuntos, Veículos de Controle Remoto, Cilindros de Rodas, Veículos a Bateria, Cilindro de Freio | visíveis | Uma aba por categoria escolhida no download (confirma P2 p.2) |
| 9 | Informações legais | visível | Links de políticas (produtos proibidos) |

Sem intervalos nomeados, sem proteção de pasta ou de aba e sem `calcChain.xml`. Em `workbook.xml`, o `<calcPr/>` está
vazio. Pelo padrão do XML (`t="str"`, `ignoredErrors`), o arquivo parece gerado por Apache POI (hipótese).

## 3. Estrutura de uma aba de categoria

| Linha | Conteúdo |
|---|---|
| 1 | Caminho da categoria ("Acessórios … > Cilindro de Freio") e títulos dos grupos de colunas (células mescladas) |
| 2 | Nome da categoria |
| **3** | **Cabeçalhos** |
| **4** | **"Obrigatório"** sob cada coluna obrigatória |
| 5 | Ajuda da coluna (limites, formato) |
| 6 | Links ("Obter URLs no gestor de fotos", "Identificar o código universal", …) |
| 7 (ou 8) | Em abas de catálogo, uma linha extra de ajuda ("Buscar o código", "Preço mínimo: 8,00…") |
| **7, 8 ou 9 → 1001** | **Linhas de dados**, já pré-preenchidas com padrões e marcadores ("Novo", "1.0", "Clássico", "Mercado Envios", "Selecionar", "Insira ou selecione um valor") |

A primeira linha de dados **muda por aba**:

| Aba | Início | Capacidade |
|---|---|---|
| Protetor de Sapatos | 7 | 995 |
| Conjuntos, Cilindros de Rodas, Cilindro de Freio | 8 | 994 |
| Veículos de Controle Remoto, Veículos a Bateria | 9 | 993 |

O MLA detecta o início pela primeira fórmula da coluna auxiliar, sem posição fixa no código.

Colunas comuns (a posição muda por aba):
- Título, Quantidade de caracteres (fórmula), Condição, Código universal, colunas "Varia por: …", Fotos, SKU,
  Estoque, Preço [R$], Descrição;
- Tipo de anúncio, Tarifa de venda (fórmula), Forma de envio, Custo de envio, Retirar pessoalmente;
- Garantia (tipo, tempo, unidade), Loja Oficial, Marca, Modelo;
- atributos da categoria;
- as auxiliares ocultas **BUYBOX_FORMULA** e **HIDDEN_PICTURES**.

As abas Conjuntos, Veículos de Controle Remoto e Veículos a Bateria começam por **"Código do catálogo ML"** (abas de
catálogo). As de autopeças trazem **"Número de peça"** (obrigatório) e **"Origem"**.

**"Resumo de erros" não existe neste arquivo.** A documentação o mostra (P2 p.4–5). Ele deve aparecer só no arquivo de
retorno (P1 p.8) ou em outra versão do modelo. Fica pendente até termos uma planilha de retorno real.

## 4. Fórmulas (por linha de dados; cerca de 3.000–4.000 por aba)

| Coluna | Fórmula (resumo) | Finalidade |
|---|---|---|
| Quantidade de caracteres | `LEN(INDIRECT(ADDRESS(ROW(), COLUMN()-1)))` | Contador do título |
| Tarifa de venda | `IF(tipo="Premium", ROUND(preço×P/100,2), IF(tipo="Clássico", ROUND(preço×C/100,2), "-"))`, com o preço achado por `SUMIF` no cabeçalho "Preço*" | Mostra a tarifa. Taxas **por categoria** no arquivo: Premium 19/16,5/17%, Clássico 14/11,5/…%. O inspetor as extrai (`fee_percent`) |
| BUYBOX_FORMULA (oculta) | Abas comuns: `IF(TRIM(A)<>"", FALSE, "")`. Abas de catálogo: `IF(OR(título<>"", código<>""), AND(código<>"", condição="novo"), "")` | **Situação da linha:** vazio = linha inativa; FALSE = anúncio comum; TRUE = anúncio de catálogo (código + "Novo") |
| Fotos (só abas de catálogo) | `IF(BUYBOX=TRUE …, "Este produto tem imagens do catálogo do Mercado Livre", "")` | Avisa que o catálogo fornece as fotos. Quem preenche substitui a fórmula pelas URLs |

Não há fórmulas de validação "de verdade": as regras ficam em validações de dados e na formatação condicional (§5).
O MLA **não** reimplementa essas fórmulas em Python.

## 5. Validações e formatação condicional (regras confirmadas pelo template)

| Regra | Como aparece no arquivo |
|---|---|
| Colunas obrigatórias | Linha 4 "Obrigatório" + formatação condicional que pinta a célula de vermelho quando a linha está ativa (BUYBOX ≠ "") e o valor está vazio ou com marcador |
| Listas fechadas | Validação `list` apontando para "extra info" com alerta de erro (`showErrorMessage`): Condição, Tipo de anúncio, Forma de envio, Custo de envio, Retirar pessoalmente, Tipo de garantia, Unidade, Loja Oficial, Gênero… |
| Listas abertas (sugestões) | `list` sem alerta: Código universal (motivos de isenção), cores, tamanhos, materiais, marcas da categoria |
| Título ≤ 60 caracteres | Formatação condicional `LEN(...) > 60` e texto de ajuda |
| **Preço mínimo 8,00** | Formatação condicional `$preço < 8.00` e ajuda "Preço mínimo: 8,00 em moeda local" |
| Números | `decimal` ≥ 0 (estoque, preço, tempo de garantia, medidas) e `ISTEXT` em vermelho |
| Textos | `textLength` ≤ 255 (SKU, Marca, Modelo) e ≤ 50.000 (Descrição) |
| Variações | Ajuda G52/G55: mesmo título genérico; "desde que não envolvam mudança de preço"; ajuda do Preço: "elas devem ter o mesmo preço"; G57: mudar cor, tamanho etc.; G58: fotos, SKU e estoque próprios |
| Fotos | Ajuda G36: "A coluna Fotos é Obrigatória"; **G45: "Você tem 2 dias para colar o URL na sua planilha e enviá-la"**, URLs separadas por vírgula, um grupo de fotos por produto |
| Catálogo | G21/G23: com código de catálogo, as células cinzas não precisam ser preenchidas. As regras condicionais de Marca/Modelo dependem de BUYBOX=FALSE |
| Prazo | Ajuda C26 "antes de 1 de dezembro" + data técnica "2026-12-01" na aba oculta → o prazo é confirmado pelo arquivo, sem ano deduzido |

## 6. Decisões para o Writer (implementado)

1. **Cópia por patch de XML.** Muda só a parte XML da aba de destino, mais `<calcPr fullCalcOnLoad="1"/>` em
   `workbook.xml`. As outras partes são copiadas byte a byte. O openpyxl **nunca grava**: ele descarta desenhos e
   imagens (a aba Ajuda tem 8) e reescreve o pacote todo.
2. **Só células de dados graváveis:**
   - entram as linhas a partir do início detectado e as colunas que não são auxiliares nem calculadas;
   - "Fotos" é exceção: é gravável, porque quem preenche substitui a fórmula;
   - cabeçalhos, a linha "Obrigatório", ajudas, links e as linhas seguintes não são tocados.
3. **Cada célula mantém seu estilo.** Texto entra como *inline string* (`sharedStrings.xml` não muda) e números como
   número. Texto começando com "=" é gravado como texto, nunca como fórmula.
4. **Padrões do arquivo preservados:** colunas sem mapeamento continuam com "Novo", "Clássico", "Mercado Envios" etc.
5. **Valores em cache das fórmulas:** nas linhas gravadas, os resultados guardados das fórmulas são removidos (estariam
   errados: comprimento 0, tarifa "-"), e o Excel é instruído a recalcular ao abrir.
6. **Verificação a cada exportação:** mesma lista e ordem de partes; partes fora da aba idênticas; mesma quantidade de
   validações, formatações, mesclas, links e colunas; nada fora de `sheetData` alterado; o arquivo reabre. Qualquer
   falha cancela a exportação.

Testes:
- arquivo sintético que reproduz este layout;
- **a cópia sanitizada do arquivo real** (teste opcional local): o writer preenche cada uma das 6 abas, todas as
  fórmulas permanecem e a verificação passa.

## 7. Riscos de compatibilidade (não resolvidos sem um envio real)

| Risco | Por quê | Como validar |
|---|---|---|
| **O ML recalcula fórmulas?** | Se o processador ler o valor guardado de BUYBOX_FORMULA sem recalcular, as linhas gravadas aparecem sem cache (o original também tinha cache vazio "") | Envio controlado de 1 produto fictício autorizado, ou abrir/salvar no Excel antes de enviar |
| Inline strings × shared strings | Excel e Apache POI leem ambos; o processador do ML não é conhecido | Mesmo envio controlado |
| Vínculo da linha 1 de "extra info" | Precisa ficar intacto (o writer não toca nessa aba) | Coberto pela verificação byte a byte |
| Prazo | Arquivo vencido é recusado ("baixe uma nova") | O MLA bloqueia a exportação após o prazo |
| URLs do Gestor válidas por 2 dias | Ajuda G45 | O MLA avisa na validação |
| Mudanças de layout pelo ML | Colunas mudam por categoria e por versão | Comparação automática entre versões do template (`compare_reports`) e reaproveitamento do mapeamento por nome de cabeçalho |
