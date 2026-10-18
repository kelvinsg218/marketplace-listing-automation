# Guia do usuário

## 1. Traga a base de produtos (Importações)
Importações → **Nova importação** → escolha o que importar (Produtos ou Compatibilidades) e o arquivo: CSV, XLSX,
JSON, XML, PDF (tabela ou ficha técnica) ou ZIP com planilha e fotos.
1. **Prévia**: confira as primeiras linhas como foram lidas (linhas marcadas “revisar” vieram ambíguas do PDF ou
   têm colunas a mais).
2. **Mapeamento**: cada coluna recebe um campo do MLA. Colunas marcadas “Provável: confirme” (ex.: `codigo`,
   `saldo`) precisam da sua confirmação. Escolha se produtos já cadastrados serão atualizados (só os campos
   preenchidos no arquivo) e, se quiser, uma pasta extra de fotos. **Salvar como modelo** reaproveita o mapeamento.
3. **Revisão**: veja o que será criado, atualizado ou ignorado, com cada alteração “atual → arquivo”, erros por
   linha e imagens encontradas. Inclua ou ignore linhas, ou use **Em massa**. Nada foi gravado ainda.
4. **Confirmar importação** grava tudo de uma vez; se cancelar durante a gravação, nada muda.
5. O relatório fica no histórico de Importações (**Exportar relatório** gera um CSV).

Fotos nomeadas pelo SKU (`ABC-1.jpg`, `ABC-1_2.jpg`) são ligadas automaticamente; use também
**Associar imagens de uma pasta**. Imagens citadas e não encontradas ficam como **mídias pendentes** no produto e
são ligadas quando você importar arquivos com o mesmo nome. O MLA nunca executa arquivos de um ZIP.

## 2. Revise o catálogo mestre (Catálogo)
Busque por nome, SKU (inclusive de variação), GTIN, código do fabricante, marca ou fornecedor; filtre por
situação, mídia pendente e grupo. **Novo produto** (Ctrl+N) ou clique duas vezes para editar. Abas: Básico,
Descrição, Técnico (especificações e atributos), Imagens (fotos, arquivos técnicos, mídias pendentes), Comercial
(preços, estoque, variações), Logística, Compatibilidade e Marketplaces. O painel à direita mostra o que falta.
Um produto fica **Pronto** com título, categoria, descrição, preço, estoque, ao menos uma imagem, peso e dimensões.

## 3. Cadastre compatibilidades (Compatibilidades)
Informe marca, modelo, versão, anos e código de referência, com a fonte. Dados do cliente entram como
**Confirmada**; fabricante e fontes externas entram como **Não verificada** até você confirmar. Use **Rejeitar**
para guardar o registro de que uma informação está errada. Importação em massa pela Central de Importações.

## 4. Cadastre as contas (Marketplaces)
**Adicionar conta**: marketplace, nome, URL da conta de vendedor (só domínios oficiais, HTTPS) e conta padrão.
Cada conta usa um navegador dedicado, separado do seu navegador pessoal. **Abrir navegador** permite entrar na conta
manualmente; **Testar conexão** verifica a sessão (o login e qualquer verificação são feitos por você). Quando a
verificação de login do marketplace ainda não está mapeada, o resultado é “Não verificada”.

## 5. Prepare os anúncios (Anúncios)
No Catálogo, selecione produtos → **Preparar anúncios** → marketplace e conta. Em Anúncios, clique duas vezes para
ajustar título, descrição, preço, estoque, categoria, atributos e imagens daquele anúncio (campos vazios usam o
catálogo). **Aprovar** quando não houver pendências; a nota de completude sugere melhorias. **Enviar aprovados
para a fila** só está disponível onde a automação existe (hoje, o marketplace simulado).

## 6. Execute e revise (Automações)
Em Automações, o MLA abre o navegador da conta, preenche o formulário e para para você conferir os valores e a
captura de tela. **Aprovar e publicar** publica e registra o código do anúncio; **Rejeitar** encerra sem publicar.
Pausar para depois do item atual. Se o app for fechado no meio, os itens voltam para a fila; um item interrompido
durante a publicação fica como **Requer intervenção**: confira no marketplace antes de reexecutar.
Grupos (Grupos → **Novo grupo**) permitem validar e executar vários produtos de uma vez.

Para conhecer o fluxo sem publicar nada, use o **Marketplace simulado**.

## 7. Histórico, backups e configurações
Histórico mostra cada tentativa com status, etapa, horário e resultado; **Exportar CSV** abre no Excel.
Configurações → **Criar backup agora** / **Restaurar selecionado**. Um backup é criado ao abrir o app e antes de
cada atualização do banco.

Atalhos: Ctrl+1…9 navegam entre as seções; Ctrl+F busca; Ctrl+D duplica; Delete exclui; Ctrl+S salva no editor.
