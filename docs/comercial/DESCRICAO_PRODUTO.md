# MLA: Marketplace Listing Automation

**Organizamos e preparamos catálogos de fornecedores para publicação em marketplaces, reduzindo o trabalho manual
de cadastro e revisão.**

## O problema
Quem vende em marketplace recebe catálogos de fornecedores em formatos diferentes: planilhas com nomes de coluna
próprios, PDFs, pastas de fotos, arquivos compactados. Antes de anunciar, alguém precisa conferir códigos, preços,
estoques, GTIN, fotos, variações e aplicações, corrigir o que veio errado e montar tudo no formato que o
marketplace pede. É um trabalho repetitivo, sujeito a erro e difícil de rastrear.

## O que o MLA faz
1. **Recebe a base do fornecedor como ela vier**: CSV, Excel, JSON, XML, PDF com tabela, ZIP com planilha e fotos ou
   uma pasta de imagens. Reconhece colunas com nomes comuns de ERP e pede confirmação quando o nome é ambíguo.
2. **Confere cada linha antes de gravar**: SKU repetido, preço com letras, GTIN com dígito errado ou estragado pelo
   Excel, estoque negativo, linhas sem código. Nada entra sem o usuário ver o motivo.
3. **Liga as fotos pelo código do produto** e marca como pendente o que foi citado e não chegou.
4. **Mantém um catálogo mestre por empresa**, com variações, especificações, compatibilidades (com fonte e
   verificação) e histórico de cada alteração, campo a campo.
5. **Permite correções em lote com segurança**: pré-visualização antes de gravar, só campos descritivos, tudo ou
   nada.
6. **Prepara os anúncios por marketplace e por conta**, aponta o que impede a aprovação e exige revisão humana.
7. **Entrega uma planilha de anúncios conferida** (uma linha por variação, fotos em pasta) e um relatório de
   pendências para devolver ao fornecedor.

## O que o MLA não faz
- Não inventa dados: GTIN, preço, estoque, medidas e compatibilidades vazios continuam vazios.
- Não publica nada sem aprovação humana e não contorna login, CAPTCHA ou bloqueios dos marketplaces.
- Ainda não publica diretamente no Mercado Livre ou na Shopee (veja [limitações](LIMITACOES_CONHECIDAS.md)).

## Para quem
- Lojistas que revendem catálogos de vários fornecedores (autopeças, utilidades, eletrônicos, acessórios).
- Agências e operadores que cadastram produtos para vários clientes: cada empresa tem dados separados.

## Como funciona na prática
Aplicativo para Windows, instalado no computador de quem opera. Os dados ficam no próprio computador, numa pasta
por empresa, com backup automático. Não há mensalidade de servidor nem envio da base para a nuvem.

## Resultado verificável
Num catálogo fictício de 300 produtos (408 linhas, 519 fotos, PDF de ficha técnica e base de aplicações com erros
intencionais), o MLA recusou as 20 linhas com erro informando o motivo, preservou 100% dos SKUs, preços, estoques e
GTIN válidos, associou 489 fotos e gerou a planilha de 266 anúncios em cerca de 7 a 12 segundos de processamento num
notebook com 5,7 GB de RAM utilizável. Esse tempo não inclui a conferência humana. Relatório completo:
[DEMO_COMERCIAL.md](../DEMO_COMERCIAL.md).

Não há ainda medição comparando com o cadastro manual; o piloto supervisionado é o lugar para medir isso com os
dados do cliente.
