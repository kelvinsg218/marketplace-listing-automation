# Auditoria técnica do MLA para o MVP comercial

**Data:** 19/10/2026 · **Base auditada:** commit `de3b310` (árvore limpa) · **Linha de base de testes:** 178 aprovados
(unidade + interface + ponta a ponta no Edge com o marketplace simulado), 0 falhos.

Fontes de evidência: leitura do código, execução da suíte de testes, demonstração visual gravada de 19/10/2026
(`docs/DEMO_TEST_REPORT.md`, 78 verificações aprovadas, 2 falhas, 2 não executadas) e pesquisa das plataformas
(links no fim). Nada abaixo foi marcado como aprovado só porque consta no README.

## 1. Stack e arquitetura
- **Linguagem/framework:** Python 3.13, PySide6 6.12 (Qt Widgets), Playwright 1.63 com o Microsoft Edge do sistema,
  SQLite (WAL, migrações SQL numeradas 0001–0007), openpyxl (XLSX), pypdf (PDF).
- **Camadas:** `ui/` (13 páginas e diálogos) → `services/` (regras de negócio) → `persistence/` (repositórios SQL) ·
  `importing/` (leitores, ZIP seguro, mapeamento, plano/gravação) · `automation/` (fila, executor em thread,
  adaptadores, perfis de navegador) · `licensing/` (placeholder, não aplicado).
- **Build:** PyInstaller one-folder (`mla.spec`). **Não há build atual em `dist/`** (o último, de 12/10, foi
  apagado/antigo e não inclui openpyxl/pypdf); precisa ser refeito e validado.
- **Dados:** `%LOCALAPPDATA%\MLA` (banco, imagens, arquivos, perfis do Edge, backups, logs). Backup automático antes
  de migrar e ao abrir.

## 2. Matriz de funcionalidades

| Funcionalidade | Implementada | Testada (automático) | Ponta a ponta | Bloqueios | Classificação | Prioridade |
|---|---|---|---|---|---|---|
| Catálogo mestre (SKU, GTIN, variações, imagens, especificações) | Sim | Sim | Sim (demo 19/10) | Preço do editor aceita letras | PARCIAL | P0 |
| Importação CSV/XLSX/JSON/XML/PDF/ZIP/pasta | Sim | Sim (34 testes) | Sim (demo) | Tela final confusa | APROVADO (ajuste visual) | P1 |
| Pré-visualização, mapeamento, duplicatas, relatório por linha | Sim | Sim | Sim | — | APROVADO | — |
| Arquivos corrompidos/maliciosos (ZIP, XML com entidades) | Sim | Parcial (sem teste de XLSX/PDF corrompido) | Parcial | — | PARCIAL | P1 |
| Compatibilidades (origem + verificação) | Sim | Sim | Sim | — | APROVADO | — |
| Grupos | Sim | Sim | Sim | — | APROVADO | — |
| **Empresa/cliente (multiempresa) e isolamento de dados** | **Não** | Não | Não | Etapa 1 do fluxo do MVP | **NÃO IMPLEMENTADO** | **P0** |
| Correção em lote segura | Não (só via reimportação) | Não | Não | Etapa 8 do fluxo | **NÃO IMPLEMENTADO** | **P0** |
| Rastreabilidade de alterações (quem/como mudou cada campo) | Parcial (só importações) | Parcial | Parcial | Edições manuais não registradas | **PARCIAL** | **P0** |
| Preparação de anúncios por conta (estados, aprovação) | Sim | Sim | Sim | — | APROVADO | — |
| **Exportação utilizável de anúncios preparados** | **Não** (só exportação do catálogo) | Não | Não | Etapa 10 do fluxo | **NÃO IMPLEMENTADO** | **P0** |
| Relatório de execução/validação para piloto | Parcial (importação + histórico CSV) | Parcial | Parcial | Falta relatório de pendências do catálogo | PARCIAL | P0 |
| Fila, revisão humana, pausa/retomada/cancelamento, recuperação | Sim | Sim | Sim (simulado) | — | APROVADO | — |
| Reexecutar pelo Histórico | Sim | Sim (fluxo por produto) | **Falha** para anúncios da tela Anúncios | Bug da demo | **FALHANDO** | **P0** |
| Publicação real Mercado Livre | Não (adaptador recusa) | Não | Não | Inspeção autorizada / API oficial com app próprio | NÃO IMPLEMENTADO | P1 (depende do dono) |
| Publicação real Shopee | Não | Não | Não | Idem | NÃO IMPLEMENTADO | P2 |
| Teste de conexão de contas | Sim | Sim (simulado) | Sim (simulado) | ML não mapeado ("Não verificada") | PARCIAL | P1 |
| Segurança do navegador (sandbox) | Não (`--no-sandbox` padrão do Playwright) | Não | — | Risco antes de contas reais | **FALHANDO** | **P0** |
| Logs sem segredos | Parcial (URLs com query string podem ir ao log) | Não | — | — | PARCIAL | P1 |
| Falhas de rede na automação | Parcial (só timeouts são repetidos) | Não | Não | — | PARCIAL | P2 |
| Dashboard | Sim | Sim | Sim | Sobreposição com 8 itens em 1366×768 | PARCIAL | P1 |
| Backup/restauração | Sim | Sim | Sim (demo) | — | APROVADO | — |
| Empacotamento Windows (.exe) | Spec existe | `--self-test` em 12/10 | **Não verificado** na versão atual | Refazer build | NÃO VERIFICADO | P0 |
| Instalador / desinstalador | Não | Não | Não | — | NÃO IMPLEMENTADO | P0 |
| Atualização do app preservando dados | Dados ficam fora da pasta do app (por projeto) | Migração testada | Não verificado com instalador | — | PARCIAL | P1 |
| Licenciamento | Placeholder (não aplicado) | Sim (fluxo) | — | Chaves forjáveis (D-011) | PARCIAL | P2 |
| Inteligência de mercado / IA | Só estrutura (contratos, tabelas) | Sim (contratos) | — | — | NÃO IMPLEMENTADO (por escopo) | P2 |

## 3. Publicação e exportação: o que as plataformas oferecem hoje (pesquisa de 19/10/2026)
- **Mercado Livre, API oficial:** publicação por `POST /items`, categoria obrigatória (ID predefinido), atributos
  obrigatórios lidos de `/categories/{id}/attributes`, GTIN condicionalmente obrigatório, **pelo menos uma foto
  obrigatória desde 23/02/2026** e um novo modelo “User Products” para desenvolvimento novo. Exige **app registrado
  no portal de desenvolvedores e autorização OAuth do vendedor** (ação humana do dono da conta).
- **Mercado Livre, Anunciador em massa:** planilha Excel **gerada por categoria dentro da conta do vendedor**, com
  campos obrigatórios marcados, regras de não alterar abas/colunas, fotos por URL (Gestor de fotos) e uma linha por
  variação; aceita também planilhas exportadas da Shopee.
- **Shopee:** Mass Upload com modelos básico/avançado baixados da Central do Vendedor; Open Platform (API) exige
  aprovação como parceiro (Partner ID/Key) e autorização da loja.
- **Consequência para o MVP:** sem um modelo oficial real em mãos, gerar a planilha oficial seria adivinhar colunas
  (proibido pelas regras do projeto). O MVP entrega uma **planilha intermediária validada** (uma linha por
  variação, colunas nomeadas como os campos oficiais mais comuns, fotos em pasta) e um **roteiro de validação
  supervisionada** para mapear o modelo oficial e/ou a API com a conta do cliente. Publicação real: **NÃO VERIFICADA**.

## 4. Desktop × web
| Critério | Evidência no repositório | Conclusão |
|---|---|---|
| Automação em navegador autenticado | Perfis persistentes do Edge por conta, login manual, Playwright local | Natural no desktop; na web exigiria navegadores remotos por cliente (custo e risco) |
| Arquivos locais (planilhas, PDFs, pastas de fotos, ZIP) | Importação lê pastas inteiras e ZIPs localmente | Desktop evita upload de GBs de fotos |
| Empacotamento | Spec PyInstaller funcional (build de 12/10 passou no self-test) | Viável agora |
| Isolamento de clientes | Inexistente hoje | Desktop: uma pasta de dados por empresa resolve sem servidor |
| Custo de hospedagem | Zero no desktop | Web exigiria servidor, armazenamento de imagens e navegadores headless |
| Reuso para SaaS | `services/`, `importing/`, `persistence/` não dependem de Qt (testados com pytest puro) | Camada de negócio já reaproveitável numa API futura |
| Atualizações | Dados fora da pasta do app; migrações com backup | Atualizar = substituir a pasta do app |

**Hipótese confirmada:** finalizar como aplicativo Windows e manter a camada de negócio independente de Qt para
uma futura API/SaaS. Nenhuma migração para web será iniciada sem aprovação.

## 5. Plano de correção (ordem)
1. **P0:** sandbox do Edge; Reexecutar pelo Histórico no fluxo de anúncios; validação estrita de valores em reais;
   multiempresa com pasta de dados isolada; edição em lote segura + histórico de alterações por campo; exportação de
   anúncios preparados + relatório de pendências do catálogo; build Windows + instalador/desinstalador testados.
2. **P1:** layout do Dashboard e da conclusão da importação; aviso duplicado de categoria; rótulo ZIP; URLs sem
   query string nos logs; testes de arquivos corrompidos.
3. **P2 (fora do MVP):** API oficial do Mercado Livre (depende de app e OAuth do dono), Shopee, inteligência de
   mercado/IA, licenças assinadas.

## Fontes
- [Mercado Livre: publicar produtos](https://developers.mercadolivre.com.br/pt_br/publicacao-de-produtos/) ·
  [atributos](https://developers.mercadolivre.com.br/pt_br/atributos) ·
  [identificadores de produtos](https://developers.mercadolivre.com.br/pt_br/identificadores-de-produtos) ·
  [publicar no catálogo](https://developers.mercadolivre.com.br/pt_br/publicacao-no-catalogo)
- [Mercado Livre: Anunciador em massa](https://vendedores.mercadolivre.com.br/nota/anuncie-varios-produtos-de-uma-vez-nuevo) ·
  [Gestor de fotos](https://vendedores.mercadolivre.com.br/nota/evite-erros-nas-fotos-da-planilha-usando-o-gestor-de-fotos)
- [Shopee: Mass Upload (Seller Education)](https://seller.shopee.sg/edu/article/7028) ·
  [guia de Mass Upload](https://cdngarenanow-a.akamaihd.net/shopee/shopee-seller-live-sg/downloads/Shopee%20Mass%20Upload%20User%20Guide%20(sg).pdf) ·
  [visão geral da Open Platform (terceiro)](https://api2cart.com/api-technology/shopee-api/)

## 6. Situação depois das correções (19/10/2026, v0.2.0)

| Funcionalidade | Antes | Depois | Evidência |
|---|---|---|---|
| Multiempresa e isolamento | NÃO IMPLEMENTADO | APROVADO | D-017; `tests/unit/test_workspaces.py`, `tests/ui/test_ui_companies.py` |
| Correção em lote segura | NÃO IMPLEMENTADO | APROVADO | D-018; `tests/unit/test_changes.py`, `tests/ui/test_ui_bulk_edit.py` |
| Rastreabilidade por campo | PARCIAL | APROVADO | Migração 0008; aba Histórico; 781 alterações no cenário comercial |
| Exportação de anúncios preparados | NÃO IMPLEMENTADO | APROVADO (planilha intermediária) | D-019; `tests/unit/test_listing_export.py`; 323 linhas sem divergência no cenário |
| Relatório para piloto | PARCIAL | APROVADO | Relatório de pendências do catálogo + modelo de relatório de piloto |
| Reexecutar pelo Histórico | FALHANDO | APROVADO | Teste de regressão em `tests/unit/test_listings.py` |
| Sandbox do navegador | FALHANDO | APROVADO | `chromium_sandbox=True`; testes de navegador e autoteste do exe |
| Valores em reais no editor | PARCIAL | APROVADO | `parse_money_strict`; `tests/unit/test_units.py` |
| Arquivos corrompidos | PARCIAL | APROVADO | 8 casos em `tests/unit/test_imports.py`; o assistente não mostra mais "erro inesperado" |
| Logs sem segredos | PARCIAL | APROVADO (URLs) | `safe_url`; teste em `tests/unit/test_accounts.py` |
| Falhas de rede na automação | PARCIAL | APROVADO (antes do clique de publicar) | D-020; `tests/automation/test_executor_retries.py` |
| Dashboard / tela Concluído | PARCIAL | APROVADO | Capturas em 1366×768 e 1100×700 |
| Empacotamento (.exe) | NÃO VERIFICADO | APROVADO nesta máquina | `tools/build_release.py`; autoteste do exe congelado |
| Instalador / desinstalador | NÃO IMPLEMENTADO | APROVADO nesta máquina; NÃO VERIFICADO em máquina limpa | `installer/`; testes manuais registrados em `comercial/GUIA_INSTALACAO.md` |
| Publicação real ML / Shopee | NÃO IMPLEMENTADO | NÃO VERIFICADO | Depende de autorização e conta do dono |

Problemas novos encontrados pelo cenário comercial e corrigidos: sinônimos de colunas de ERP, GTIN inválido chegando
ao anúncio, mídia pendente duplicada com caminho local, foto corrompida não registrada, título da janela repetido.
