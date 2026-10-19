# Relatório da demonstração e teste geral do MLA

**Data:** 19/10/2026 (execução definitiva das 14:01 às 14:11, com gravação de 9 min 50 s)
**Versão:** 0.1.0 + etapa “Catálogo Mestre Inteligente” (código do commit `e9f3c30`; nenhuma funcionalidade alterada
durante a demonstração)
**Ambiente:** Windows 11, tela 1366×768, Microsoft Edge (perfil dedicado da conta simulada), Python 3.13

## Como foi feito
- O aplicativo **real** foi aberto pelo código-fonte com uma **pasta de dados isolada**: `demo/demo-data`. Nenhum
  dado real foi usado ou alterado (os arquivos de `%LOCALAPPDATA%\MLA` continuam com a data de 18/10, 14:40).
- Um roteiro visível (`demo/run_demo.py`) navegou pelas telas, clicou e digitou com pausas, com uma faixa de
  narração na parte de baixo da tela. Todo o catálogo é fictício (empresa “Horizonte Autopeças”), gerado por
  `demo/make_fixtures.py`.
- Só o **marketplace simulado** foi automatizado. Nenhuma conta real de Mercado Livre ou Shopee foi aberta.
- O roteiro fez o papel do usuário em três pontos, e isso aparece na narração:
  - digitou o login e clicou no CAPTCHA no navegador simulado;
  - clicou em **Continuar**, **Aprovar** e **Rejeitar**;
  - informou caminhos de arquivo no lugar dos diálogos nativos do Windows, que não podem ser automatizados.
- Cada resultado foi conferido **no banco de dados**, e não apenas na tela.
- Os resultados ficam em `demo/output/demo-results.json`; a tabela completa está no fim deste relatório.

## Resumo
| Situação | Quantidade |
|---|---|
| Teste realizado com sucesso | 78 |
| Teste com falha | 2 (1 bug de produto, 1 bug de fluxo) |
| Teste não executado | 2 |
| Observações registradas | 5 |

## Funcionalidades testadas e aprovadas
- **Dashboard:** abre com dados reais do banco, navegação lateral completa (11 telas) e atualização após as operações
  (15 produtos, 4 publicações simuladas, 1 em preparação no Mercado Livre).
- **Catálogo mestre:**
  - cadastro manual completo: identificação, GTIN, fornecedor, descrição, informações técnicas, especificações,
    2 imagens, 2 variações com SKU próprio, logística;
  - validação ao vivo, incluindo GTIN com dígito verificador inválido;
  - status “Pronto”, edição, busca por SKU de variação, duplicação e exclusão de dado de teste.
- **Central de Importações (todos os formatos, conferidos no catálogo):**
  - **CSV** do ERP (Windows-1252): 6 criados e 2 erros por linha (SKU repetido, preço inválido). Fotos ligadas pela
    coluna e pelo SKU no nome do arquivo; foto ausente virou mídia pendente; relatório exportado.
  - **XLSX** com aba de capa: aba de dados escolhida sozinha; alterações exibidas como “atual → arquivo”;
    3 atualizações sem perder imagens nem descrição; 1 produto novo.
  - **JSON** aninhado, com correção manual do mapeamento (fabricante.marca → Marca), e **XML** com SKU em atributo.
  - **PDF:** linhas seguras importadas; a linha ambígua ficou em “Revisar” e não entrou sem decisão.
  - **ZIP:** produto criado com a foto do pacote; o `instalar.bat` foi bloqueado e não foi extraído.
  - **Pasta de fotos por SKU:** mídia pendente resolvida e fotos ligadas.
  - **Cancelamento** durante a gravação de 3.000 linhas: nada foi gravado. O **descarte** ficou registrado no
    histórico de importações.
- **Compatibilidades:**
  - cadastro manual (dado do cliente, já confirmado) e edição;
  - importação em massa: 4 novas, 1 repetida identificada, 1 SKU inexistente recusado;
  - fonte externa entra como “Não verificada”;
  - filtros, confirmar e rejeitar, busca e aba no produto.
- **Grupos:** criar, adicionar e remover produtos, renomear, escolher o marketplace e validar.
- **Marketplaces e contas:**
  - conta simulada e conta fictícia do Mercado Livre;
  - URL de domínio falso recusada (`mercadolivre.com.br.golpe.com`) e URL válida normalizada;
  - edição, conta padrão e perfil do Edge próprio de cada conta;
  - teste de conexão (só no simulado) reaproveitou a sessão salva no perfil.
- **Preparação de anúncios:**
  - 6 anúncios preparados do catálogo; o produto incompleto gerou anúncio “Incompleto”;
  - edição com título, descrição e preço próprios, sem alterar o produto mestre;
  - aprovação individual e em lote (o incompleto foi recusado com o motivo) e filtro “Precisam de correção”;
  - no Mercado Livre, o envio à fila fica bloqueado com aviso.
- **Automação (marketplace simulado):**
  - fila, abertura do Edge, login simulado, preenchimento, upload de imagens, revisão humana, publicação simulada
    confirmada e status/ID atualizados no MLA;
  - **Pausar** (termina o item atual), **Retomar**, CAPTCHA simulado tratado como ação manual, **Rejeitar** na
    revisão, **Cancelar execução**;
  - **prevenção de duplicata** (“Já publicado nesta conta”, `104-mensagem-resultado-da-execução.png`);
  - **recuperação após reiniciar:** MLA fechado no meio do preenchimento; ao reabrir, o item voltou para a fila, os
    dados persistiram e o item terminou depois de retomado.
- **Histórico:** execuções concluídas e canceladas, filtros, busca, detalhes passo a passo e CSV exportado com uma
  linha por execução (confere com o banco: 7 execuções, 4 publicadas).
- **Configurações:** backup manual, exclusão de um produto de teste e **restauração** que o devolveu (ambiente
  isolado). **Licença:** chave inválida recusada, nada ativado. **Logs:** gravados na pasta da demonstração, 2 avisos
  esperados (pedidos de ação manual).

## Funcionalidades com falha (bugs encontrados)
| # | Gravidade | Problema | Como reproduzir | Evidência |
|---|---|---|---|---|
| 1 | Média | **Reexecutar no Histórico recusa anúncios preparados na tela Anúncios.** O botão usa o fluxo por produto, que exige o marketplace ativado na aba Marketplaces do produto. Contorno que funcionou: editar, reaprovar e reenviar pela tela Anúncios. | Preparar e aprovar um anúncio pela tela Anúncios → rejeitar na revisão → Histórico → Detalhes → Reexecutar | `demo/screenshots/106-mensagem-resultado-da-execução.png` |
| 2 | Baixa | **Campo de preço do editor aceita letras e as descarta em silêncio:** `12,3x` vira R$ 12,30 sem aviso. A importação já é estrita; o editor não. | Catálogo → Novo produto → Comercial → preço `12,3x` | `004-editor-preco-invalido.png` |

## Problemas visuais e de usabilidade
- **Dashboard, “Atividade recente”:** com 8 itens na tela de 1366×768, o nome do produto se sobrepõe à linha de
  baixo (`128-dashboard-final.png`; com menos itens fica correto, `115-…`).
- **Importação, passo “Concluído”:** grandes espaços vazios. O rótulo “Linhas com erro na gravação” aparece sem
  tabela, e o resumo chama de “ignorado(s)” as linhas com erro (`015-csv-5-relatorio.png`).
- **Editor de anúncio:** “Categoria do marketplace não definida” aparece duas vezes, como aviso e como dica de
  completude (`086-anuncio-editor.png`).
- **Histórico de importações:** a coluna Tipo mostra “Produtos, Arquivo” para ZIP (`061-…`).
- **Anúncios:** o seletor de conta corta nomes longos (“Loja Demo ML (f…”, `089-…`).
- **Duas formas de configurar marketplace:** a aba Marketplaces do produto (preço e categoria por marketplace)
  convive com a tela Anúncios (preço e categoria por conta). Isso pode confundir e está na origem do bug 1.

## Testes não executados
- **Teste de conexão com Mercado Livre e Shopee:** não executado por regra; contas reais não são acessadas.
- **Falha real de etapa e “Requer intervenção”:** o marketplace simulado não oferece, pela interface, um modo de
  falha definitiva. Uma categoria inexistente vira “Outros” com aviso, e o tempo mínimo por etapa é 5 s. Esses
  caminhos são cobertos pelos testes automatizados de navegador, não pela demonstração.
- **Seleção de arquivos pelo explorador do Windows, “Abrir anúncio” e “Abrir captura”:** diálogos e programas
  externos não automatizáveis ou bloqueados na demonstração. Os arquivos foram informados pelo roteiro.

## Funcionalidades ainda não implementadas
- Publicação real no Mercado Livre e na Shopee: a inspeção autorizada da conta real ainda está pendente.
- Coleta de dados de concorrentes e agentes de IA: só existe a estrutura de dados, sem telas.
- OCR de PDF digitalizado, imagens embutidas em XLSX e download de imagens por link.
- Telas de regras por categoria e de consentimento de IA, e associação de imagem a uma variação no editor.
- Instalador, licenças assinadas e teste em máquina limpa.

## Observações técnicas
- **Segurança:** o Edge da automação abre com o aviso “`--no-sandbox` … riscos de estabilidade e segurança”, que é o
  padrão do Playwright (`093-…`). Recomenda-se abrir com o sandbox ligado antes de usar contas reais.
- **Desempenho:** a análise de 3.000 linhas e a gravação rodaram em segundo plano, com progresso visível e a
  interface responsiva. Cada anúncio simulado levou de 9 a 20 s, incluindo as pausas da demonstração. Uso de
  memória e CPU não foi medido.
- **Roteiro de demonstração:** usar o `QtTest` para digitar fora de um executor de testes derrubava o processo
  (código 0xC0000409 no `Qt6Core.dll`). O roteiro passou a usar cliques nativos (`animateClick`) e inserção de
  texto. Isso não afeta o uso normal do MLA.

## Melhorias recomendadas
1. Reexecutar pelo Histórico deve reenviar o **anúncio** (fluxo de anúncios) quando ele existir (bug 1).
2. Validar estritamente os campos em reais do editor, como a importação já faz (bug 2).
3. Ligar o sandbox do Edge (`chromium_sandbox=True`) na abertura do perfil dedicado.
4. Unificar a configuração por marketplace na tela Anúncios, deixando a aba do produto só com valores padrão.
5. Ajustar o layout de “Atividade recente” e do passo “Concluído” da importação para telas de notebook.
6. Remover o aviso duplicado de categoria no editor de anúncio e mostrar “ZIP” no histórico de importações.

## Gravação e capturas
- **Gravação:** `demo/recordings/mla-demo-20261019-1401.mp4`. MP4/H.264, 1280×720, 5 fps, 9 min 50 s, 31 MB, sem
  áudio. Contém só as janelas do MLA e do navegador do marketplace simulado (sem tela inteira, sem notificações).
  A barra de endereço do navegador mostra o caminho local do projeto. Arquivo local, fora do Git.
- **Capturas:** `demo/screenshots/` (128 imagens numeradas na ordem da demonstração). Também fora do Git.
- **Saídas:** relatório da importação CSV (`demo/output/importacao-1.csv`), histórico exportado
  (`demo/output/historico-20261019-1410.csv`) e resultados (`demo/output/demo-results.json`).
- **Para repetir:** `.venv\Scripts\python demo\run_demo.py`. A variável `MLA_DEMO_SPEED=2` acelera as pausas e
  `MLA_DEMO_NOREC=1` desliga a gravação.

## Próximas prioridades
1. Corrigir os bugs 1 e 2 e os ajustes de layout, com testes.
2. Ligar o sandbox do Edge.
3. Com a sua autorização e a URL da conta, fazer a inspeção somente leitura do Mercado Livre e mapear o
   formulário real.
4. Criar as telas de regras por categoria, consentimento de IA e imagem por variação.
5. Reconstruir o executável e preparar o instalador.

## Apêndice: todas as verificações
Gerado de `demo/output/demo-results.json` por `demo/results_table.py`.


#### Geral

| Resultado | Verificação | Detalhe |
|---|---|---|
| Observação | Pasta de dados da demonstração: C:\Users\garci\projetos\MLA\demo\demo-data |  |

#### A. Dashboard

| Resultado | Verificação | Detalhe |
|---|---|---|
| Sucesso | Dashboard abre com dados reais do banco (vazio) | 0 produtos no catálogo. Atualizado segunda às 14:01. |
| Sucesso | Todos os botões de navegação abrem a tela certa |  |

#### B. Catálogo mestre

| Resultado | Verificação | Detalhe |
|---|---|---|
| Sucesso | Editor mostra pendências ao vivo antes de preencher |  |
| Sucesso | GTIN com dígito verificador inválido é sinalizado |  |
| Falha | Preço em formato inválido é recusado |  |
| Sucesso | Cadastro fica Pronto quando completo | Pronto |
| Sucesso | Produto salvo com 2 imagens, 2 variações, GTIN e especificações | imagens=2 variações=2 |
| Sucesso | Edição gravada (preço R$ 84,90) |  |
| Sucesso | Busca por SKU de variação |  |
| Sucesso | Duplicação cria cópia com SKU novo |  |
| Sucesso | Exclusão remove só a cópia |  |

#### C. Central de Importações

| Resultado | Verificação | Detalhe |
|---|---|---|
| Sucesso | CSV: 6 novos e 2 linhas com erro (SKU repetido e preço inválido) | {'create': 6, 'error': 2} |
| Sucesso | CSV: 6 produtos conferidos no catálogo | HZ-FIL-01, HZ-PAS-02, HZ-VEL-03, HZ-PAL-04, HZ-LAM-05, HZ-TAP-06 |
| Sucesso | CSV: fotos ligadas pela coluna e pelo SKU no nome (HZ-PAS-02 com 2 imagens) |  |
| Sucesso | CSV: foto encontrada só pelo SKU (HZ-PAL-04) |  |
| Sucesso | CSV: foto citada e ausente vira mídia pendente (HZ-LAM-05) |  |
| Sucesso | CSV: preço e GTIN convertidos (HZ-FIL-01 R$ 29,90) |  |
| Sucesso | CSV: relatório da importação exportado | C:\Users\garci\projetos\MLA\demo\output\importacao-1.csv |
| Sucesso | XLSX: 3 atualizações e 1 produto novo | {'create': 1, 'update': 3} |
| Sucesso | XLSX: alteração exibida com valor atual e novo |  |
| Sucesso | XLSX: preço e estoque atualizados sem perder imagens nem descrição |  |
| Sucesso | XLSX: produto novo criado (HZ-CAP-08) |  |
| Sucesso | JSON: produtos criados com marca do campo aninhado e fotos pendentes |  |
| Sucesso | XML: 2 produtos criados |  |
| Sucesso | PDF: 2 linhas seguras e 1 para revisar | {'create': 2, 'review': 1} |
| Sucesso | PDF: linha ambígua não foi gravada sem decisão (HZ-TRI-15 ausente) |  |
| Sucesso | ZIP: produto criado com a foto de dentro do pacote |  |
| Sucesso | ZIP: arquivo .bat não foi extraído | [] |
| Sucesso | Pasta: mídia pendente resolvida (HZ-LAM-05 com foto) |  |
| Sucesso | Pasta: fotos adicionadas aos produtos do JSON |  |
| Sucesso | Cancelamento: nenhum produto gravado e importação volta para revisão | antes=15 depois=15 situação=planned |
| Sucesso | Importação descartada |  |
| Sucesso | Catálogo com os 15 produtos esperados (1 manual + 14 importados) | 15 produtos |

#### D. Compatibilidades

| Resultado | Verificação | Detalhe |
|---|---|---|
| Sucesso | Compatibilidade manual salva como confirmada (cliente) |  |
| Sucesso | Edição da compatibilidade gravada |  |
| Sucesso | Importação de compatibilidades: 4 novas, 1 repetida e 1 SKU inexistente | ['create', 'create', 'create', 'create', 'unchanged', 'error'] |
| Sucesso | Compatibilidades do cliente gravadas e confirmadas |  |
| Sucesso | Fonte externa entra como não verificada |  |
| Sucesso | Confirmar e rejeitar compatibilidades | {'HB20': <Verification.CONFIRMED: 'confirmed'>, 'Sandero': <Verification.REJECTED: 'rejected'>} |
| Sucesso | Busca de compatibilidade por modelo |  |
| Sucesso | Aba Compatibilidade do produto lista os registros |  |

#### E. Grupos

| Resultado | Verificação | Detalhe |
|---|---|---|
| Sucesso | Grupo criado |  |
| Sucesso | 3 produtos adicionados ao grupo |  |
| Sucesso | Produto removido do grupo (continua no catálogo) |  |
| Sucesso | Grupo renomeado e com marketplace de destino |  |
| Observação | Validação do grupo exibida: Todos os 2 produtos estão prontos para os marketplaces escolhidos. |  |

#### G. Marketplaces e contas

| Resultado | Verificação | Detalhe |
|---|---|---|
| Sucesso | Conta simulada criada |  |
| Sucesso | URL de domínio falso é recusada | O endereço precisa ser do Mercado Livre (mercadolivre.com.br). |
| Sucesso | Conta ML fictícia salva com URL normalizada (sem teste de conexão) |  |
| Sucesso | Edição da conta gravada |  |
| Sucesso | Conta padrão alterada |  |
| Sucesso | Cada conta tem um perfil de navegador próprio dentro da pasta de dados do MLA | {'Loja Demo ML (fictícia)': 'browser-profiles\\mercadolivre-5', 'Conta principal': 'browser-profiles\\shopee-2', 'Conta de teste': 'browser-profiles\\simulado-3', 'Loja Demo Simulada': 'browser-profiles\\simulado-4'} |

#### F. Preparação de anúncios

| Resultado | Verificação | Detalhe |
|---|---|---|
| Sucesso | 6 anúncios preparados a partir do catálogo | {'HZ-SUP-20': 'ready', 'HZ-PAS-02': 'ready', 'HZ-FIL-01': 'ready', 'HZ-VEL-03': 'ready', 'HZ-CAP-08': 'incomplete', 'HZ-LAM-05': 'ready'} |
| Sucesso | Produto incompleto gera anúncio Incompleto (HZ-CAP-08) |  |
| Sucesso | Anúncio editado e aprovado; produto mestre intacto |  |
| Sucesso | Aprovação em lote recusa o incompleto com motivo | 2 aprovado(s). Pendências:  Capa protetora para carro: Escolha a categoria do produto. |
| Sucesso | Estados após aprovação | {'HZ-SUP-20': 'approved', 'HZ-PAS-02': 'approved', 'HZ-CAP-08': 'incomplete', 'HZ-FIL-01': 'approved', 'HZ-VEL-03': 'ready', 'HZ-LAM-05': 'ready'} |
| Sucesso | Envio para a fila bloqueado no Mercado Livre |  |

#### H. Automação no marketplace simulado

| Resultado | Verificação | Detalhe |
|---|---|---|
| Sucesso | 3 anúncios aprovados na fila (preparado ≠ publicado) | ['HZ-SUP-20', 'HZ-PAS-02', 'HZ-FIL-01'] |
| Sucesso | 1º anúncio: login simulado, preenchimento, upload de imagens, revisão e publicação simulada |  |
| Sucesso | Status atualizado no MLA com ID do anúncio simulado | SIM-MVFIDDEN |
| Sucesso | 2º anúncio publicado durante a pausa (termina o item atual) |  |
| Sucesso | Fila parada após o item atual | paused |
| Observação | Item rejeitado na revisão: HZ-FIL-01 |  |
| Sucesso | CAPTCHA simulado tratado como ação manual | ['O marketplace pediu uma verificação. Resolva no navegador e clique em Continuar.'] |
| Sucesso | Rejeitar na revisão encerra sem publicar | cancelled |
| Sucesso | Execução duplicada bloqueada | 0 anúncio(s) entraram na fila.  Não incluídos: Suporte veicular magnético (Marketplace simulado): Já publicado nesta conta (SIM-MVFIDDEN). |
| Falha | Reexecutar pelo Histórico um anúncio preparado na tela Anúncios | 0 anúncio(s) entraram na fila.  Não incluídos: Filtro de óleo (Marketplace simulado): Marketplace simulado não está ativado no cadastro do produto. |
| Bug encontrado | Reexecutar no Histórico usa o fluxo por produto e exige o marketplace ativado no cadastro do produto; anúncios preparados pela tela Anúncios (sem essa marcação) são recusados. Contorno: editar e reaprovar o anúncio na tela Anúncios e enviar de novo. |  |
| Sucesso | Anúncio rejeitado reenviado e publicado |  |
| Sucesso | Execução cancelada: nenhum item publicado | [('HZ-VEL-03', 'cancelled'), ('HZ-LAM-05', 'cancelled')] |
| Sucesso | Após reiniciar, o item interrompido volta para a fila e os dados persistem | produtos=15 |
| Sucesso | Item recuperado concluído após retomar |  |
| Não executado | Falha real de etapa e “Requer intervenção” | O marketplace simulado não oferece pela interface um modo de falha definitiva (categoria ausente vira “Outros” com aviso; tempo mínimo por etapa é 5 s). Esses caminhos são cobertos pelos testes automatizados de navegador |

#### G. Teste de conexão (simulado)

| Resultado | Verificação | Detalhe |
|---|---|---|
| Sucesso | Conexão simulada verificada com a sessão salva no perfil | Sessão ativa como demo@feiralocal.test. |
| Não executado | Teste de conexão com Mercado Livre/Shopee | Não executado por regra: contas reais não são acessadas. |

#### I. Histórico e relatórios

| Resultado | Verificação | Detalhe |
|---|---|---|
| Sucesso | Histórico confere com o banco (publicados) | tela=4 banco=4 cancelados=3 total=7 |
| Sucesso | Detalhes mostram o registro passo a passo | 5 registros |
| Sucesso | CSV do histórico exportado com uma linha por execução | historico-20261019-1410.csv: 7 linhas |

#### J. Configurações, backup, licença e logs

| Resultado | Verificação | Detalhe |
|---|---|---|
| Sucesso | Backup criado | mla-20261019-141103-369388-manual.db |
| Sucesso | Produto de teste excluído antes da restauração |  |
| Sucesso | Restauração devolve o produto excluído |  |
| Sucesso | Chave inválida recusada sem ativar nada | Formato de chave inválido. Exemplo: MLA-PROFESSIONAL-XXXX-XXXX-XXXX |
| Sucesso | Log do aplicativo gravado na pasta de dados da demonstração | C:\Users\garci\projetos\MLA\demo\demo-data\logs\mla.log |
| Observação | Resumo do log (logscan): 1413 linhas / INFO=1403, WARNING=2 / L1335: WARNING mla.automation item=1 step=login Intervenção manual necessária: Entre na sua conta no navegador aberto e depois clique em Continuar. / L1353: WARNING mla.automation item=3 step=open_form Intervenção manual necessária: O marketplace pediu uma verificação. Resolva no navegador e clique em Continuar. |  |

#### A. Dashboard final

| Resultado | Verificação | Detalhe |
|---|---|---|
| Sucesso | Dashboard reflete produtos e publicações (simuladas) | produtos=15 publicados=4 |
| Observação | Gravação salva em C:\Users\garci\projetos\MLA\demo\recordings\mla-demo-20261019-1401.mp4 (2870 quadros) |  |
