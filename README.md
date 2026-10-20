# MLA — Marketplace Listing Automation

Aplicativo desktop para Windows que mantém um catálogo mestre de produtos, importa bases completas de clientes,
prepara anúncios por marketplace e por conta e automatiza o preenchimento no navegador, parando para a sua
revisão antes de qualquer publicação.

Apresentação visual (capturas de tela e página para portfólio): repositório
[marketplace-listing-automation-showcase](https://github.com/kelvinsg218/marketplace-listing-automation-showcase).

## Status
v0.2.0 (MVP para piloto supervisionado). Tudo o que está em “O que já funciona” é coberto por testes automatizados
(230: unidade, interface e ponta a ponta no Edge com o marketplace simulado) e foi exercitado num cenário de 300
produtos fictícios com métricas medidas ([docs/DEMO_COMERCIAL.md](docs/DEMO_COMERCIAL.md)). A **publicação real no
Mercado Livre e na Shopee não está verificada**; hoje o MLA entrega uma planilha de anúncios conferida e o fluxo
completo de publicação roda no marketplace simulado. Pacote comercial em [docs/comercial/](docs/comercial/README.md);
detalhes técnicos em [docs/CURRENT_STATUS.md](docs/CURRENT_STATUS.md).

## O que já funciona
- **Empresas (clientes):** uma pasta de dados isolada por empresa (catálogo, imagens, contas, sessões, backups,
  logs) e troca de empresa dentro do app.
- **Histórico e correção em lote:** cada alteração de produto registrada campo a campo com a origem; edição em
  lote de campos descritivos com pré-visualização (preço, estoque, GTIN e SKU nunca em lote).
- **Exportação:** planilha intermediária de anúncios (XLSX/CSV, uma linha por variação, fotos copiadas, abas de
  pendências e resumo) e relatório de pendências do catálogo para o fornecedor.
- **Catálogo mestre:** SKU principal e de variações, código do fabricante, GTIN/EAN (dígito verificador conferido),
  marca, modelo, categoria, fornecedor, nome comercial; custo, preço de venda e promocional, estoque e estoque
  mínimo, unidade, garantia, condição, situação comercial; descrição original e técnica, material, cor, peso,
  dimensões, especificações, atributos personalizados, referências do fabricante, observações internas; imagens,
  variações, arquivos técnicos e mídias pendentes. Campos novos opcionais; checagem ao vivo do que falta.
- **Busca e organização:** busca por nome, SKU (inclusive de variação), GTIN, código do fabricante, marca ou
  fornecedor; filtros por situação, mídia pendente e grupo; carregamento incremental; duplicação, exclusão e
  exportação em CSV ou JSON (o JSON inclui variações; as imagens são copiadas junto).
- **Central de Importações:** CSV, XLSX, JSON, XML, PDF (tabela ou ficha técnica), ZIP com planilha e fotos e pasta
  de imagens pelo SKU. Prévia, reconhecimento de colunas com confirmação dos nomes ambíguos, modelos reutilizáveis,
  validação por linha, duplicatas, variações pelo SKU pai, alterações exibidas “atual → arquivo”, decisões
  criar/atualizar/ignorar, gravação em uma única transação (cancelar não altera nada), relatório e histórico.
  Executáveis, scripts e planilhas com macro em ZIPs são ignorados e nunca executados.
- **Compatibilidades:** marca, modelo, versão, anos, referência, fonte e verificação; dados do cliente entram
  confirmados, demais fontes como não verificadas; nada é inferido; importação em massa.
- **Preparação de anúncios:** um anúncio por produto, marketplace e conta, guardando só o que difere do produto;
  estados Rascunho, Incompleto, Pronto para revisão, Aprovado, Na fila, Em execução, Publicado confirmado, Falha e
  Requer intervenção; aprovação desfeita se o conteúdo mudar; nota de completude calculada sem IA.
- **Contas de marketplace:** várias contas, conta padrão, URL do vendedor validada pelo domínio oficial, navegador
  Edge dedicado e isolado por conta, teste de conexão com login manual.
- **Automação:** fila persistente (um item por vez), pausa, retomada, cancelamento, recuperação após fechar o app,
  prevenção de duplicados, capturas e registro de cada etapa, revisão humana obrigatória antes de publicar;
  execução individual, em grupo ou em lote. Grupos de produtos com ordem e marketplaces de destino.
- **Dashboard e histórico:** pipeline do catálogo e dos anúncios, pendências, situação por marketplace, histórico
  com filtros, detalhes, reexecução segura e exportação CSV.
- **Marketplace simulado** embutido para testar o fluxo inteiro sem publicar nada de verdade.
- **Estrutura para inteligência de mercado e IA** (sem telas, sem coleta e sem IA ativa): URLs de referência e
  observações com fonte e data, contrato para coletores com trava de permissão, sugestões de IA guardadas à parte
  e aplicadas só com aceite, bloqueio de provedores externos sem autorização.

## Princípios
- Nada é publicado sem aprovação; “publicado” só com confirmação do marketplace.
- Login, CAPTCHA e verificações são sempre feitos pelo usuário.
- Dados locais em `%LOCALAPPDATA%\MLA`, com backup automático antes de cada atualização do banco.
- Importações nunca apagam registros nem substituem dados sem mostrar a alteração.
- Dados do cliente, informações externas e sugestões de IA ficam separados.

## Ainda não disponível
- Publicação real no **Mercado Livre** e na **Shopee** (depende de autorização da conta e de validação
  supervisionada do formulário real ou da API oficial); preenchimento do modelo oficial de envio em massa.
- Coleta automática de dados de concorrentes e agentes de IA (apenas a estrutura existe).
- Imagens embutidas em XLSX, download de imagens por link, PDF digitalizado (OCR) e foto por variação automática.
- Assinatura digital do executável, atualização automática, cobrança e servidor de licenças.
- Lista completa: [docs/comercial/LIMITACOES_CONHECIDAS.md](docs/comercial/LIMITACOES_CONHECIDAS.md).

## Tecnologia
Python 3.13 · PySide6 (Qt) · SQLite (WAL, migrações versionadas) · Playwright com Microsoft Edge · openpyxl ·
pypdf · pytest.

## Começar
- Cliente: [instalação](docs/comercial/GUIA_INSTALACAO.md), [manual rápido](docs/comercial/MANUAL_RAPIDO.md) e
  [guia de importação](docs/comercial/GUIA_IMPORTACAO.md).
- Usuário (guia completo): [docs/USER_GUIDE.md](docs/USER_GUIDE.md) e [docs/INSTALLATION.md](docs/INSTALLATION.md).
- Desenvolvimento: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md), [docs/TESTING.md](docs/TESTING.md),
  [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/DECISIONS.md](docs/DECISIONS.md).
- Estado do projeto: [docs/CURRENT_STATUS.md](docs/CURRENT_STATUS.md) e [docs/NEXT_STEPS.md](docs/NEXT_STEPS.md).

```powershell
.venv\Scripts\python -m pip install -e .[dev]
.venv\Scripts\python -m mla                       # abre o aplicativo
.venv\Scripts\python -m pytest -m "not browser"   # testes rápidos
```
