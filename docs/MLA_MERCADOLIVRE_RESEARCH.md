# Pesquisa — Anunciador em Massa do Mercado Livre

Registro de 01/11/2026. Classificação usada:
- **Confirmado:** lido diretamente numa fonte oficial do Mercado Livre nesta sessão.
- **Indício:** vem de terceiros ou de trecho indexado por buscador. Pode estar desatualizado e **não serve de base para
  implementação**.
- **Desconhecido:** sem fonte.

## 1. Acesso às duas documentações oficiais

| Link | Leitura direta | Navegador local (Edge headless, perfil temporário) | Resultado |
|---|---|---|---|
| [anuncie-varios-produtos-de-uma-vez-nuevo](https://vendedores.mercadolivre.com.br/aprender/nota/anuncie-varios-produtos-de-uma-vez-nuevo) | HTTP 403 | HTTP 403, página "Hubo un error accediendo a esta pagina" | **Não lida** |
| [entenda-como-preencher-sua-planilha-excel...](https://vendedores.mercadolivre.com.br/nota/entenda-como-preencher-sua-planilha-excel-para-anunciar-em-m) | HTTP 403 | HTTP 403, mesma página | **Não lida** |

Também devolveram 403: a Central de Ajuda (`mercadolivre.com.br/ajuda/...`) e o portal de desenvolvedores
(`developers.mercadolivre.com.br`). O bloqueio é por tráfego automatizado. Não tentei contorná-lo: nada de troca de
user-agent, navegador visível imitando um humano, proxy ou uso do perfil do seu navegador, conforme as regras do
projeto. **Nenhuma das duas páginas foi analisada.** Este documento não substitui essa leitura.

## 2. O que foi confirmado (fontes oficiais lidas)

API pública `api.mercadolibre.com`, consultada sem autenticação em 01/11/2026:

| Endpoint | Status | O que confirma |
|---|---|---|
| `GET /categories/{id}/attributes` | 200 | Cada atributo traz `id`, `name`, `value_type`, `value_max_length`, `hint`, `hierarchy`, `attribute_group_*` e `tags` (ex.: `{"required": true, "catalog_required": true}` em `BRAND` de MLB1055) |
| `GET /sites/MLB/domain_discovery/search?q=...` | 200 | Sugere `domain_id`, `category_id`, `category_name` e atributos a partir de um texto (ex.: "filtro de oleo" → MLB47120) |
| `GET /sites/MLB/listing_types` | 403 (`PA_UNAUTHORIZED_RESULT_FROM_POLICIES`) | Exige autenticação. Os tipos de anúncio não podem ser lidos anonimamente |

Consequência: a API pública pode **complementar** a validação, cruzando os atributos obrigatórios da categoria com as
colunas do template. Isso não substitui o template, e a API não informa o layout da planilha.

O app desktop já integra a API oficial (OAuth + PKCE, validação sem publicar). Ver `docs/GUIA_MERCADO_LIVRE.md`.

## 3. Indícios (terceiros e trechos indexados): não implementar com base nisto

Fontes: artigo no LinkedIn de 24/10/2019 (Octavio Hozawa); blog da Lexos de 05/06/2024; trecho do link oficial nº 1
exibido pelo buscador; relato no Reclame Aqui de 2024; FAQ da VTEX.

- **Caminho:** Anúncios → Anunciar → "Ir para Anunciador em massa" → escolher categorias → baixar o Excel. O envio é
  feito pela mesma área ("Enviar a planilha Excel"). (Lexos, 2024)
- **A planilha é gerada por conta e por categorias escolhidas.** Cada categoria teria a própria aba. "Só podem ser
  enviadas planilhas baixadas da sua própria conta." Uma planilha "só pode ser usada uma vez": para novos produtos,
  baixa-se outra. (LinkedIn, 2019; trecho indexado)
- **Preenchimento:** obrigatórios marcados com `(*)`. Não renomear nem adicionar abas. Não apagar colunas coloridas
  (podem ser ocultadas). "N/A" ou "Não aplica" quando faltam dados de ficha técnica ou código universal. (2019)
- **Imagens:** por **URL pública** hospedada fora do ML. (2019)
- **Variações:** uma linha por variação, repetindo título e demais dados, mudando os atributos da variação (cor,
  tamanho) e, se for o caso, SKU, código universal e fotos. Em categorias de catálogo, cada variação viraria um anúncio
  separado. (2019)
- **Catálogo:** coluna "FORMA DE ANUNCIAR", com código de catálogo obtido por link na própria planilha. (2019)
- **Limite:** 10.000 anúncios por dia. (2019 e trecho indexado)
- **Erros:** depois do envio dá para baixar uma nova planilha só com as linhas que falharam, com indicação do que
  corrigir. Uma coluna "Resumo de erros" aparece no trecho indexado. O envio não pode ser interrompido, e o aviso de
  término chega por e-mail. (2019 e trecho indexado)
- **Alteração de anúncios existentes:** é outra ferramenta ("Alterar/Modificar em massa"), com outra planilha.
- **Diferenças por categoria:** um relato de 2024 diz que a planilha exigiu EAN para kits, coisa que o cadastro manual
  não pedia. A VTEX diz que atributos obrigatórios variam por categoria.

## 4. O que falta e decisões que dependem disso

| Pergunta | Situação | Bloqueia |
|---|---|---|
| Estrutura real do XLSX: abas, linha de cabeçalho, linhas de ajuda, colunas ocultas | Desconhecido | Leitor de templates e exportação |
| Validações de dados (listas), intervalos nomeados, abas ocultas com domínios, fórmulas, proteção | Desconhecido | Preenchimento seguro sem quebrar o arquivo |
| Metadados que vinculam a planilha à conta e às categorias | Desconhecido (indício de que existe) | Regra "preencher cópia do arquivo oficial" |
| Imagens por URL ou upload | Indício: URL pública | Armazenamento público de imagens (decisão de segurança) |
| Variações (linhas repetidas e agrupamento) | Indício de 2019 | Mapeamento de variações |
| Formato da planilha de erros devolvida | Indício (coluna "Resumo de erros") | Importação de resultados (etapa E) |
| Limite diário e tamanho máximo por arquivo | Indício de 10.000/dia | Divisão de lotes |
| Diferenças entre MLB e outros países | Desconhecido | Fora do escopo inicial (só MLB) |

## 5. Pedido ao usuário (necessário antes da etapa D)

1. **Conteúdo das duas páginas oficiais:** salvar como PDF (Ctrl+P → Salvar como PDF) ou copiar o texto, com as
   imagens. O bloqueio atinge tráfego automatizado; no seu navegador elas devem abrir. Coloque em `docs/ml-research/`
   (pasta ignorada pelo git: templates da sua conta podem conter identificadores e não devem ir para o repositório).
2. **Templates oficiais intactos baixados da sua conta,** sem preencher, de 2 ou 3 categorias diferentes:
   - uma de autopeças (o seu caso de uso);
   - uma com variações (ex.: roupa ou calçado);
   - uma categoria simples sem variações.
3. **Se tiver:** uma planilha já enviada e a planilha de erros devolvida pelo ML (de preferência com dados fictícios).

Com os arquivos em mãos, a análise prevista é: abrir com openpyxl (sem macros) e listar abas e estados (visível/oculta/
very hidden), linhas de cabeçalho, `data_validations`, nomes definidos, fórmulas, proteção, estilos de coluna e
propriedades customizadas. O resultado vira a seção "Estrutura confirmada" deste documento.

## 6. Princípios já decididos (valem com ou sem os arquivos)

- **Preencher cópias do arquivo oficial**, nunca gerar um XLSX "parecido". O template original fica guardado
  imutável, com hash SHA-256, e cada exportação parte de uma cópia.
- O sistema não declara anúncio publicado só porque gerou ou enviou uma planilha. O estado vem de evidência
  (planilha de resultado importada) ou de confirmação explícita do usuário.
- Valores obrigatórios nunca são inventados. Campo sem dado vira erro de validação, a menos que o usuário escolha
  explicitamente um valor padrão.
- Antes de qualquer etapa nova sobre a planilha, a regra correspondente precisa estar confirmada no template ou numa
  fonte oficial lida.
