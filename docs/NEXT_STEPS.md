# Próximos passos

## Ações humanas necessárias
1. **Publicar a release `v0.1.2-beta` no showcase** (público) com `MLA-Setup-0.1.2-beta.exe` + `.sha256`, pelo
   site do GitHub ([passo a passo](BUILD_E_DISTRIBUICAO.md#publicar-uma-versão)). Sem isso, o botão Atualizações
   responde "Nenhuma versão publicada".
2. **Segundo computador:** enviar o instalador ao seu amigo com o
   [roteiro](ROTEIRO_TESTE_SEGUNDO_COMPUTADOR.md) e receber a tabela preenchida + logs.
3. **Mercado Livre:** criar o seu aplicativo no portal de desenvolvedores e conectar a conta
   ([guia](GUIA_MERCADO_LIVRE.md)); rodar "Validar no Mercado Livre (sem publicar)" em 2 ou 3 anúncios.
4. **Publicação real:** decidir se e quando autoriza um teste supervisionado de publicação com um produto escolhido.
5. **Assinatura de código** (certificado pago) para eliminar o aviso do SmartScreen antes de distribuir mais.

## Desenvolvimento, por prioridade
- Publicação supervisionada pela API (POST /items + upload de fotos via /pictures) atrás de confirmação explícita,
  depois do passo 4.
- Variações e fotos na validação do Mercado Livre.
- Associar fotos às variações; distinguir arquivo corrompido de não encontrado nas mídias pendentes.
- Desinstalador sem console (hoje é um script PowerShell).

## MLA Web 2.0
Ações humanas:
1. **Templates reais (bloqueiam o writer):** no Anunciador em massa da sua conta, baixe sem editar: (a) uma categoria
   de autopeças; (b) uma categoria com variações; (c) se possível, uma gerada por código universal ou link. Coloque em
   `docs/ml-research/` (ignorada pelo git). Lista em [MLA_MERCADOLIVRE_RESEARCH.md §8](MLA_MERCADOLIVRE_RESEARCH.md).
2. **Planilha de retorno com "Resumo de erros"** (bloqueia o importador de erros), se conseguir gerar uma com dados
   de teste.
3. **RLS no PostgreSQL 18 local:** rode uma vez, no PowerShell, na raiz do projeto:
   `& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -f infra\postgres\init.sql`
   (pede a senha do superusuário definida na instalação). Depois o teste de RLS roda com o papel `mla`.
4. **Desktop:** atualizar
   `tests/ui/test_ui_master_catalog.py::test_listing_page_blocks_queue_for_marketplace_without_automation` para a nova
   mensagem da API oficial, que é seu trabalho em andamento em `src/mla/ui/pages/listings.py`.

Desenvolvimento: (1) com os templates, rodar o inspetor nos arquivos reais e escrever a seção 9 da pesquisa; (2) só
então o Workbook Writer, que preenche uma cópia e é testado comparando o XML interno com o original; (3) etapa C:
Central de Importações (CSV/XLSX primeiro) com fila PostgreSQL e worker, compatibilidades e edição em lote.
