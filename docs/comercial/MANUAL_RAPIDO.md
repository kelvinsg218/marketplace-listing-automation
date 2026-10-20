# Manual rápido

Do arquivo do fornecedor à planilha de anúncios conferida, em 8 passos.

**1. Escolha a empresa.** No canto superior esquerdo, o botão com o nome da empresa abre a lista. **Nova
empresa…** cria uma área com dados separados (catálogo, fotos, contas, sessões, backups). Cada cliente numa
empresa.

**2. Importe a base.** Importações → **Nova importação** → escolha o arquivo (CSV, Excel, JSON, XML, PDF, ZIP).
- **Prévia:** confira se as linhas foram lidas certo.
- **Mapeamento:** cada coluna recebe um campo. As marcadas "Provável: confirme" precisam do seu OK.
- **Revisão:** veja o que será criado, atualizado ou ignorado, com o motivo de cada linha recusada. Nada foi gravado.
- **Confirmar importação:** grava tudo de uma vez (cancelar não altera nada). O passo "Concluído" lista as linhas a
  corrigir na planilha de origem.

**3. Ligue as fotos.** Importações → **Associar imagens de uma pasta**. Fotos com o SKU no nome (`ABC-1.jpg`,
`ABC-1_2.jpg`, `ABC-1-3.jpg`) são ligadas sozinhas. As que faltarem ficam como "mídia pendente" no produto.

**4. Confira o catálogo.** Catálogo: filtre por situação (Rascunho, Incompleto, Pronto) e por mídia pendente.
Clique duas vezes para editar; o painel à direita diz o que falta. A aba **Histórico** mostra cada alteração, com a
origem.

**5. Corrija em lote, se precisar.** Selecione vários produtos → **Editar em lote** → marque os campos (categoria,
marca, fornecedor, garantia…) → **Pré-visualizar alterações** → **Aplicar**. Preço, estoque, GTIN e SKU não mudam
em lote.

**6. Prepare os anúncios.** Selecione produtos prontos → **Preparar anúncios** → marketplace e conta. Em Anúncios,
abra cada um para ajustar título, preço ou fotos daquele anúncio e **Aprovar** quando não houver pendência.

**7. Exporte.** Anúncios → **Exportar planilha**: gera o Excel com uma linha por variação, a pasta de fotos e as abas
"Pendências" e "Resumo". Para o fornecedor: Catálogo → **Importar e exportar → Relatório de pendências do catálogo**.

**8. Guarde a segurança.** Configurações → **Criar backup agora** antes de mudanças grandes. O MLA também faz
backup ao abrir.

## Regras que o MLA segue
- Nada é inventado: o que veio vazio continua vazio.
- Nada é publicado sem a sua aprovação; login e CAPTCHA são sempre feitos por você.
- A planilha exportada é intermediária: confira e copie para o modelo oficial do marketplace.
