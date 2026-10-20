# Funcionalidades comprovadas (versão 0.2.0)

"Comprovada" aqui significa: existe teste automatizado que passa **e** a função foi exercitada com dados fictícios
na demonstração visual (19/10/2026) ou no cenário comercial medido (19/10/2026). Suíte completa: **230 testes
aprovados, 0 falhos** (incluindo 9 de ponta a ponta no Microsoft Edge com o marketplace simulado).

| Funcionalidade | Como foi verificada |
|---|---|
| Empresas (clientes) com dados separados e troca de empresa no app | Testes de isolamento (mesmo SKU em duas empresas, contas e sessões separadas) e de troca de janela |
| Importação de CSV (UTF-8 e Windows-1252), XLSX (inclusive com aba de capa), JSON, XML, PDF com tabela, ZIP com planilha e fotos, pasta de fotos | 45 testes de importação; demonstração visual; cenário de 300 produtos |
| Reconhecimento de colunas com nomes de ERP e confirmação dos nomes ambíguos | Testes de mapeamento; no cenário, 19 de 20 colunas sugeridas |
| Validação por linha com motivo (preço inválido, GTIN em notação científica, estoque negativo, SKU repetido, linha sem SKU) | Testes; cenário: 20 de 20 linhas com erro recusadas, nenhuma entrou |
| GTIN com dígito verificador errado: guardado como veio, com aviso, e bloqueado na aprovação do anúncio | Teste; cenário: 7 de 7 anúncios exportados com o bloqueio |
| Variações pelo SKU pai, com estoque por variação | Testes; cenário: 40 produtos com 100 variações conferidas uma a uma |
| Fotos ligadas pelo SKU do produto; fotos citadas e não encontradas ou corrompidas ficam como pendentes | Testes; cenário: 489 fotos associadas, 3 arquivos corrompidos marcados como pendentes |
| Arquivos danificados ou não suportados recusados com mensagem (XLSX/PDF/ZIP corrompidos, vazio, só cabeçalho, .docx) | 8 testes |
| ZIP seguro: executáveis, scripts e planilhas com macro nunca extraídos nem executados; XML com entidades recusado | Testes; demonstração visual |
| Compatibilidades com fonte e verificação; só as confirmadas vão para a planilha | Testes; cenário: 150 criadas, 6 recusadas |
| Histórico de alterações campo a campo, com a origem (edição manual, importação nº, edição em lote) | Testes; cenário: 781 alterações registradas |
| Edição em lote de campos descritivos com pré-visualização, tudo ou nada; preço, estoque, GTIN e SKU bloqueados | Testes de unidade e de interface |
| Preparação de anúncios por marketplace e conta, com pendências e aprovação humana desfeita se o conteúdo mudar | Testes; demonstração visual |
| Exportação da planilha de anúncios (XLSX/CSV, uma linha por variação, fotos copiadas, abas Pendências e Resumo) | Testes; cenário: 323 linhas conferidas contra a origem, 0 divergências |
| Relatório de pendências do catálogo para devolver ao fornecedor | Testes; cenário: 48 pendências de 22 produtos |
| Proteção contra fórmulas maliciosas em planilhas exportadas | Testes (XLSX e CSV) |
| Fila de automação com revisão humana, pausa, cancelamento, recuperação após fechar o app e reexecução segura | Testes de ponta a ponta no marketplace simulado |
| Repetição automática de etapas em falha de rede antes do clique de publicar (nunca no clique) | Testes |
| Navegador dedicado por conta, com sandbox do Edge ativo; login e CAPTCHA sempre feitos pela pessoa | Testes de navegador |
| Backup automático ao abrir e antes de atualizar o banco | Testes; demonstração visual |
| Instalador por usuário (sem administrador), atualização preservando dados, desinstalação mantendo dados | Testado nesta máquina de desenvolvimento: instalar, verificar, abrir, recusar instalar com o app aberto, atualizar, desinstalar; dados reais conferidos intactos |

## Não comprovado (não prometer)
- Publicação real no Mercado Livre ou na Shopee: **não verificada**.
- Instalação em um computador limpo (sem Python e sem ferramentas de desenvolvimento): **não verificada**.
- Ganho de tempo em relação ao cadastro manual: **não medido**.
