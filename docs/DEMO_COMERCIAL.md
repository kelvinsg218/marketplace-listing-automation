# Cenário comercial de demonstração: catálogo fictício de 300 produtos

**Data:** 19/10/2026 · **Script:** `demo/pilot_scenario.py` (reproduzível; semente fixa) · **Base de código:** após o
commit da exportação de anúncios (item 5 de `docs/PROGRESSO_MVP.md`).

Todos os dados são **fictícios**: empresa "Aurora Autopeças", produtos, códigos, GTIN com prefixo 200 (faixa de uso
interno, nunca um produto real), veículos com nomes inventados ("Marca Alfa Modelo X1"), compatibilidades
inventadas. O script grava apenas em `demo/pilot/` (ignorado pelo Git), numa pasta de dados isolada; os dados reais
do usuário não são tocados. Nada foi publicado em marketplace.

## 1. Dados de entrada gerados

| Arquivo | Conteúdo |
|---|---|
| `catalogo-aurora.xlsx` | Aba de capa + aba "Catálogo" com 408 linhas e 20 colunas com nomes de ERP ("Cód. Produto", "Descrição do item", "Comp (cm)"…): 300 produtos (260 simples + 40 com 2 ou 3 variações = 100 linhas de variação) e erros intencionais |
| `fotos/` | 519 arquivos: 510 fotos 900×900 nomeadas pelo SKU (`SKU.jpg`, `SKU_2.jpg`, `SKU-3.jpg`), 10 fotos nomeadas pelo SKU da variação, 6 fotos sem produto e 3 arquivos corrompidos |
| `ficha-tecnica-fornecedor.pdf` | Tabela com material, garantia e cor de 28 produtos; 2 linhas com célula vazia |
| `aplicacoes-veiculos.csv` | 156 linhas de compatibilidade de 60 produtos, incluindo 4 SKUs inexistentes e 2 com anos invertidos |

Erros intencionais na planilha: 5 preços inválidos (`12,3x`, `abc`, `R$ --`, `9,99 reais`, `1O,00`), 8 GTIN com
dígito verificador errado, 4 GTIN em notação científica, 3 estoques negativos, 6 SKUs repetidos, 2 linhas sem SKU,
12 produtos sem título e descrição, 10 produtos sem foto.

## 2. Resultado por etapa

| Etapa | Resultado medido |
|---|---|
| Mapeamento de colunas | 19 de 20 colunas sugeridas automaticamente; 2 delas como "prováveis" (pedem confirmação do usuário: "Cód. Produto" e "Descrição do item"); 1 ajuste manual ("Cor da variação" → atributo da variação) |
| Análise da planilha | 408 linhas: 388 aceitas, **20 recusadas com o motivo** (5 preços, 4 GTIN em notação científica, 3 estoques negativos, 6 SKUs repetidos, 2 sem SKU) |
| Gravação | 288 produtos + 100 variações criados; 20 recusados; nenhuma falha de gravação |
| GTIN com dígito errado (8) | Importados **com aviso**, com o código exatamente como veio (dado do cliente preservado), e **bloqueados na preparação do anúncio** (7 exportados com pendência bloqueante; o 8º não tem foto e não chegou a ser preparado) |
| Associação de fotos por SKU | 489 fotos associadas a 279 produtos; 27 nomes de arquivo (cada um com suas fotos numeradas) sem produto correspondente: 6 sem produto, 10 nomeados pelo SKU da variação, 11 de produtos recusados na análise; 3 arquivos corrompidos ficaram como mídia pendente |
| PDF do fornecedor | 26 produtos atualizados; 2 linhas ambíguas ficaram para decisão humana (não incluídas automaticamente) |
| Compatibilidades | 150 criadas; 6 recusadas (4 SKUs inexistentes, 2 anos invertidos) |
| Situação do catálogo | 266 prontos, 22 incompletos (12 sem título e descrição, 9 sem foto, 1 sem estoque) |
| Edição em lote | Garantia aplicada a 36 produtos da categoria Filtros, após pré-visualização de 36 alterações |
| Preparação de anúncios | 266 anúncios para a conta de teste do Mercado Livre: 259 prontos para revisão, 7 incompletos (GTIN inválido) |
| Exportação | Planilha intermediária com 323 linhas (uma por variação) e 469 fotos copiadas; relatório de pendências do catálogo com 48 linhas (22 produtos com pendência bloqueante) |
| Histórico | 781 alterações registradas por campo, cada uma com a origem (importação, edição em lote) |

## 3. Integridade (conferência automática contra os dados de origem)

| Verificação | Resultado |
|---|---|
| SKUs válidos da origem presentes no catálogo | 288 de 288 |
| Linhas com erro que entraram no catálogo | 0 |
| SKUs inesperados no catálogo | 0 |
| Preços divergentes da origem | 0 |
| Estoques ou variações divergentes | 0 |
| GTIN divergentes (válidos e inválidos guardados como vieram) | 0 |
| Linhas da planilha exportada divergentes da origem (SKU, preço, GTIN) | 0 de 323 |
| GTIN inválido bloqueado no anúncio exportado | 7 de 7 |

Nenhum GTIN, preço, estoque, medida ou compatibilidade foi inventado: campos vazios na origem continuam vazios e só
compatibilidades confirmadas vão para a planilha (as não verificadas são apenas contadas).

## 4. Tempo e memória (medidos)

Máquina: Windows 11 (build 26200), processador AMD (8 núcleos lógicos), **5,7 GB de RAM utilizável** informada pelo
Windows, Python 3.13.5. Processo sem interface (o mesmo código de serviço usado pela interface).

| Etapa | 1ª execução (s) | 2ª execução (s) |
|---|---|---|
| Importação XLSX (análise + plano + gravação) | 0,60 | 1,18 |
| Associação de fotos (análise + gravação) | 8,89 | 2,96 |
| PDF do fornecedor | 0,45 | 0,46 |
| Compatibilidades | 0,06 | 0,07 |
| Edição em lote (pré-visualização + gravação) | 0,03 | 0,04 |
| Preparação de 266 anúncios | 0,16 | 0,16 |
| Exportação (planilha + 469 fotos) | 1,53 | 1,62 |
| Relatório de pendências | 0,15 | 0,12 |
| **Total do fluxo** | **11,87** | **6,61** |
| Pico de memória do processo | 81 MB | 77 MB |

A 1ª execução veio logo após gerar as fotos (geração: 11,3 s, não incluída no total); a 2ª reaproveitou os mesmos
arquivos. A diferença está quase toda na leitura das 519 fotos (cache de disco do Windows). Os tempos não incluem o
tempo humano de conferir o mapeamento, revisar e aprovar anúncios.

**Não há comparação com o processo manual**: nenhuma medição de cadastro manual foi feita, portanto este relatório
não afirma economia de tempo. Para afirmar, é preciso medir o mesmo catálogo feito à mão no piloto.

## 5. Problemas encontrados por este cenário e corrigidos

1. **Nomes de coluna comuns de ERP não eram reconhecidos** ("Descrição do item", "Título para anúncio",
   "Comp/Larg/Alt (cm)", "Marca/Modelo do veículo"): sem o nome mapeado, as 408 linhas eram recusadas. Sinônimos
   adicionados; "Descrição do item" entra como provável (o usuário confirma).
2. **GTIN com dígito verificador inválido passava para o anúncio**: agora bloqueia a aprovação do anúncio,
   mantendo o código original no catálogo para correção.
3. **Mídia pendente duplicada e caminho local gravado no produto**: o mesmo arquivo citado por nome e por caminho
   completo virava duas pendências, e o caminho `C:\…` do computador ficava no cadastro (e iria para relatórios do
   cliente). Agora a pendência é única por nome de arquivo e caminhos locais não são gravados.

## 6. Limitações observadas (não corrigidas neste ciclo)

- Fotos nomeadas pelo SKU da **variação** não são associadas automaticamente (10 nomes de arquivo); a associação
  de foto por variação ainda é manual.
- Arquivos de imagem corrompidos aparecem como "mídia pendente" (não encontrada), sem dizer que o arquivo existe
  mas está danificado.
- A planilha exportada é intermediária: o preenchimento do modelo oficial do Mercado Livre/Shopee (gerado por
  categoria na conta do vendedor, com fotos por link) continua sendo etapa supervisionada.
- O fluxo foi medido sem interface; a interface usa os mesmos serviços, mas a revisão humana não foi cronometrada.

## 7. Como reproduzir

```
.venv\Scripts\python -X utf8 demo\pilot_scenario.py           # gera os dados e executa
.venv\Scripts\python -X utf8 demo\pilot_scenario.py --reuse   # reaproveita os dados gerados
```

Resultados completos em `demo/pilot/results.json`; planilha e relatório em `demo/pilot/output/`. O script termina
com código 1 se qualquer verificação de integridade falhar.
