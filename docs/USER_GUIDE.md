# Guia do usuário

## 1. Cadastre um produto
Produtos → **Novo produto** (Ctrl+N). Preencha as abas; o painel à direita mostra o que falta. Um produto pode ser
salvo incompleto. Ele fica **Pronto** quando tem título, categoria, descrição, preço, estoque, ao menos uma imagem,
peso e dimensões da embalagem. Na aba **Marketplaces**, ative onde ele será anunciado e, se quiser, defina preço
próprio, categoria do marketplace e atributos conhecidos (ex.: `Modelo=X1; Cor=Preto`).

Imagens: arraste arquivos JPG, PNG ou WEBP, arraste as miniaturas para ordenar e use **Definir como principal**
para a capa. O MLA guarda uma cópia, então você pode mover ou apagar o arquivo original.

## 2. Organize em grupos (opcional)
Grupos → **Novo grupo**, adicione produtos, ordene, marque os marketplaces e use **Validar** e **Executar grupo**.
Um produto pode estar em vários grupos.

## 3. Execute e revise
Selecione produtos e clique em **Executar** (ou execute um grupo). Em **Automações**:
1. O MLA abre um navegador próprio para cada conta (separado do seu navegador pessoal).
2. Se o site pedir login ou verificação, faça no navegador aberto e clique em **Continuar**.
3. Com o formulário preenchido, confira os valores e a captura de tela. Corrija o que quiser no navegador.
4. **Aprovar e publicar** publica e registra o código do anúncio; **Rejeitar** encerra sem publicar.

Pausar faz a fila parar depois do item atual. Se o app for fechado no meio, os itens voltam para a fila; um item
interrompido durante a publicação fica como **Verificar manualmente** — confira no marketplace antes de reexecutar.

Para conhecer o fluxo sem publicar nada, ative **Marketplace simulado** no produto.

## 4. Consulte o histórico
Histórico mostra cada tentativa com status, etapa, horário e resultado. Clique duas vezes para ver o registro
completo, abrir a captura de tela ou **Reexecutar** com segurança. **Exportar CSV** abre no Excel.

## 5. Backups e configurações
Configurações → **Criar backup agora** / **Restaurar selecionado**. Um backup é criado ao abrir o app (ajustável).
Lá também ficam o navegador usado, o tempo máximo por etapa e o número de novas tentativas.

## Importar planilha
Produtos → Importar e exportar → Importar CSV. Colunas: `sku;internal_name;title;category;subcategory;brand;model;
condition;description;features;material;package_contents;warranty;price;stock;weight_g;length_cm;width_cm;
height_cm;package_type;availability_days;shipping_notes;marketplaces;images`. Preço como `129,90`; marketplaces
separados por vírgula (`mercadolivre,shopee`); imagens separadas por `|`. Exporte um CSV para ver um modelo.

Atalhos: Ctrl+1…8 navegam entre as seções; Ctrl+F busca; Ctrl+D duplica; Delete exclui; Ctrl+S salva no editor.
